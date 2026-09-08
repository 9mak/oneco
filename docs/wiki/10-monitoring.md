# 監視・アラート体制

「何が・どこで・どう通知されるか」の全体図。個別の対応手順は [docs/RUNBOOK.md](../RUNBOOK.md)。

## 全体図

```
外形監視      uptime-check.yml (30分毎)
              Cloud Run /health・Vercel トップ・/areas/東京都・収集鮮度(last_collected_at) → 失敗で Discord

Secret 監視   secret-health.yml (日次 JST9:00)
              Groq / Threads トークンを実呼び出し、401/403 → Discord

収集ラン監視   collector 実行 (GCP Cloud Run Jobs / フォールバック data-collector.yml) 内
              _send_run_summary_alert() [__main__.py]
              ├ 失敗率 > 20%              → CRITICAL (Discord。GCP 実行は Slack 未設定)
              ├ 連続失敗サイト            → WARNING
              ├ ゼロ件回帰 (baseline比較)  → WARNING
              ├ フィールド欠損率ドリフト   → WARNING
              ├ 初回から欠損 (T149)        → WARNING (site×field ごと7日に1回)
              └ auto-fix dispatch 失敗    → WARNING

掲載数監査     weekly-count-audit.yml (週次 JST日曜1:00) → scripts/site_count_audit.py
              adapter 非経由で実サイト一覧と API 公開数を突き合わせ、乖離 (|delta| が
              閾値以上) を Discord へ通知

致命フィールド監査 field-accuracy-audit.yml (月次 JST毎月1日10:00) → scripts/full_publication_audit.py
              adapter 出力と API を突き合わせ、致命8フィールドの食い違いと
              週次掲載数監査の盲点ホストの掲載漏れ疑いを Discord へ通知

Workflow 失敗  各 workflow の「Notify Discord on failure」ステップ

課金アラート   GCP 予算 (oneco-monthly-cap-500, ¥500/月) を budget-alerts topic 経由で
              2つの Cloud Function が独立購読
              ├ 90% 到達  → budget-alert が Discord 通知（早期警告、緩和措置なし）
              └ 100% 到達 → stop-billing が課金解除（メール通知のみ、Discord 無し。→ RUNBOOK F 節）
```

## 各監視の詳細

### 外形監視（`uptime-check.yml`）

- 3 エンドポイントを curl で HTTP 200 検証、3 回リトライで flap 誤検知を回避
- `/areas/東京都` を含めるのは「トップは 200 なのに SSR サブルートだけ 500」という盲点（PR #229 の /areas 500 事件）の再発検知のため
- 収集鮮度チェック: `/health` の `last_collected_at` が `FRESHNESS_MAX_HOURS`（既定 26h）より古ければ失敗。collector 実行そのものが起動できず無音で1日分の収集が飛ぶ障害（2026-08-06 の GitHub Actions 障害で発生）は、job 内からの失敗通知では原理的に拾えないため、公開データの鮮度という症状を外部から見て検知する（PR #268）
- 失敗時: Discord 通知 + workflow 自体も failure にする二重ガード

### Secret 失効監視（`secret-health.yml` → `scripts/monitoring/check_secret_health.py`）

- 背景: Groq key が約 6 週間 silent 失効し、SNS 投稿文がフォールバックテンプレに劣化していた事故
- 401/403 のみ失効と判定して通知。5xx / timeout は通知しない（誤報防止）
- 実装は `infrastructure/secret_health.py`

### 収集品質監視（`__main__.py`）

- 収集本体は 2026-08-14 に GCP Cloud Run Jobs（`oneco-collector`, `asia-northeast1`, 0:00 JST 起動）へ移設した。通知ロジック自体は `__main__.py` の `_send_run_summary_alert()` にあり、GCP 実行でも GitHub Actions フォールバック（`data-collector.yml`）実行でも同じコードパスで発火する
- GCP 実行には `DISCORD_WEBHOOK_URL` のみ Secret Manager 経由で渡している（`SLACK_WEBHOOK_URL` は未登録）。Slack 通知は GitHub Actions フォールバック実行時のみ発火する
- 閾値は `ONECO_MAX_FAIL_RATIO` / `ONECO_MAX_ZERO_RATIO` で調整可能
- 状態は `data/broken_sites.yaml` / `data/site_baselines.yaml` / `data/field_quality_drift.yaml` に永続化（→ [データフロー](02-data-flow.md)）
- 検知結果は [自己修復ループ](04-self-healing.md) のトリガーにもなる

### フィールド提供台帳 (T148/T149)

- 背景: 欠損率監視は「adapter が壊れて取れなくなった」と「元サイトがそもそもそのフィールドを公開していない」を区別できなかった。大分譲渡猫（品種欄が無い）・愛媛譲渡予定（同）のように、後者は監視上は 100% 欠損のまま**恒久的に赤く**なる。区別しないまま「初回から100%欠損」を鳴らすと、これらが毎回鳴ってオオカミ少年化し、本当の抽出漏れが埋もれる（一次調査記録: CCC `projects/oneco/outputs/breed-null-survey-20260907.md` / `phone-null-survey-20260907.md`）
- `sites.yaml` の各サイトエントリに `fields: {breed: false}` のように書くと、そのサイトはそのフィールドを提供していないと宣言できる (`SiteConfig.fields`)。キーを省略したフィールドはデフォルトで「提供している」扱い
- **一次ソースでページを実際に確認したものだけを書く**（推測禁止）。根拠は各エントリのコメントに調査記録の日付を残す
- `compute_missing_rates()` は `provided` 引数でこの台帳を受け取り、`False` のフィールドを結果から丸ごと除外する。history にも記録されないため、ドリフト検知にも T149 検知にも一切乗らない
- T148: 監視対象フィールド (`MONITORED_FIELDS`) に `species` / `breed` を追加（従来は欠損トラッカーの監視対象外で抽出漏れが監視をすり抜けていた）。`species` は `AnimalData` 側で '犬'/'猫'/'その他' の3値必須 (required) だが、`quality_metrics.is_missing()` は `species == 'その他'`（見出し・「種類」列のどちらからも犬/猫を判別できなかったフォールバック値。T156 愛媛収容中8件が実例）を欠損として扱う field 別ルールを持つ（reviewer 指摘 F-02, 2026-09-08）。ただし「値はあるが実体と食い違う」誤分類（例: 実際は猫なのに正常な形で犬と誤判定される）は捉えられない点は変わらない — その種の誤分類検知には別途サンプリング監査 (`site_count_audit.py` / `full_publication_audit.py` 系) が必要
- T149: `FieldQualityTracker.detect_never_populated()` が、台帳上「提供している」フィールドの直近3run（履歴がそれ未満なら現有全run）がすべて99%以上欠損している site×field を検知する。ドリフト検知（急増）では捉えられない「最初からずっと壊れている」ケースを別枠で拾う。同一 (site, field) の再通知は7日に1回に抑制する（`last_never_alert_at` を `data/field_quality_drift.yaml` に記録）。通知文言例: `⚠️ 初回から欠損: <site> / <field> 直近3回 100% 欠損（台帳では提供あり）`
- `scripts/field_ledger_report.py` — サイトごとに台帳の提供有無と直近欠損率を並べて表示し、「100%欠損なのに台帳では not-provided と宣言されていない」候補を一覧する。台帳を拡張するときのワークリストとして使う（`python3 scripts/field_ledger_report.py`）。CI/workflow には未組込みで手動実行前提。**新しいフィールドを `MONITORED_FIELDS` に追加する PR は、マージ前に本番 `data/field_quality_drift.yaml`（`9mak/oneco-state`、deploy-key管理の別リポジトリ）に対してこのスクリプトを実行し、初回 run で never-populated アラートが何件出るかを事前に見積もってから進めること**（T148 PR #335 は breed 追加時にこれを怠り、phone の台帳未整備 (`fields: {phone: false}` 未設定) を見落としたまま初回運用に入りかけた。reviewer 指摘 F-01, 2026-09-08。通知本文自体も `NEVER_POPULATED_NOTIFY_CAP`（既定20件）で洪水化を防いでいるが、根本対策は台帳を先に埋めること）

### 掲載数監査（`weekly-count-audit.yml` → `scripts/site_count_audit.py`, T046/T105/T141）

- adapter を経由せず実サイト一覧ページを直接 fetch し、独立シグナル (一覧セレクタで拾えるリンク数・ゼロ表現・ページ送り有無) と API 公開数をホスト単位で突き合わせる。adapter 自体が系統的に取り漏らすケース (ページ送り未対応) を adapter 経由の監査 (下記) とは独立に検出する
- 一覧セレクタは `data_collector.infrastructure.list_selector_resolution.resolve_list_selector()` で `SiteAdapterRegistry` から adapter class の `LIST_LINK_SELECTOR` → `ROW_SELECTOR` → sites.yaml の `list_link_pattern` の優先順で解決する (T141)。adapter を instantiate しないため HTTP/DB は発生しない。以前は sites.yaml の `list_link_pattern` のみを見ており、adapter が実際に使うセレクタと独立の手入力値でトートロジーだったため 213 サイト中 178 サイトが構造的に比較不能だった (T133)。registry 解決導入によりホスト単位の比較可能数がおよそ13ホスト→79ホスト (T140/T141 実装時点の sites.yaml 実測) へ拡大している
- ページ送りは `resolve_pagination()` で adapter の `NEXT_PAGE_SELECTOR` / `MAX_LIST_PAGES` を引き、`count_pattern_links_paginated()` が循環検知・上限打ち切りを行いながら最後まで辿る (`WordPressListAdapter.fetch_animal_list()` と同じ方針)。打ち切った (`pagination_truncated=True`) サイトは pattern_count が不完全な下限値になるため、そのホストは undercount/overcount 判定 (`comparable`) から除外する
- 大分・沖縄・徳島の掲載漏れ (T132) はいずれもページ送り未追従が原因で、セレクタ解決だけでは再現できない。`tests/scripts/test_site_count_audit.py::TestCountPatternLinksPaginated::test_follows_pagination_and_counts_all_pages` がこの型の回帰を固定する
- 通知閾値 (T141): comparable ホスト急増によるノイズを避けるため、Discord 通知は `|pattern_total - api_count|` が `max(2, API件数の20%)` 以上のホストに限る (`data_collector.infrastructure.count_audit_notify`)。上位15件を |delta| 降順で表示し、残りは「他 N 件」に集約する。ただし全滅（API>0 なのに掲載候補0、またはその逆）は件数に関係なく閾値をバイパスして必ず通知する（reviewer 指摘 F-01, 2026-09-08）。全件 (閾値未満も含む) は artifact の `reports/site_count_audit_*.md` に残る
- `zero_suspect` (API 0件なのに掲載候補シグナルがある) は件数差ではなく質的判定のため閾値の対象外

### 致命フィールド監査（`field-accuracy-audit.yml` → `scripts/full_publication_audit.py`, T045/T046/T101/T140）

- adapter の出力を `adapter.normalize()` まで通した上で公開 API の全件と突き合わせ、致命8フィールド (status/phone/source_url/location/prefecture/category/species/image_urls) の食い違い (`field_mismatch`) を検出する
- 掲載漏れ疑い (`adapter_only`: adapter には見えるが API に無い) のうち、上記の週次掲載数監査が構造的に比較できないホスト (`count_audit_blind_hosts()`, `resolve_list_selector()` で選択できない or PDF セレクタ or `requires_js`) に属するものだけを、コンパクトな形式 (サイトごとの件数 + 代表 URL 最大3件) で Discord 通知に含める (T140)。件数の乖離判定自体は原則週次掲載数監査の担当のため、その担当領域と重複しない範囲だけをここで拾う
- `count_audit_blind_hosts()` は週次掲載数監査の `comparable` 判定と対称になるよう `list_selector_resolution.resolve_list_selector()` を共有する。二重実装すると片方だけ直して判定がズレるため、必ず両スクリプトがこのモジュールを参照する
- `api_only` (もういない疑い) は「消し忘れ」であり公開品質ゲートに効かないため通知対象外
- 単日の掲載入れ替わりを含みうるため、通知本文には確定情報として扱わない注記を含め、`--recheck` での再照合を促す

### 課金/予算監視（`infra/stop-billing` + `infra/budget-alert`）

- 月額予算 ¥500（`oneco-monthly-cap-500`）到達で Cloud Function `stop-billing` が `oneco-app` の課金を自動解除し、Cloud Run 含む全リソースが止まる（2026-07-30 の無料トライアル失効停止事故の再発防止）
- 100%到達の通知は GCP 標準の予算アラートメール（50/90/100%閾値）のみで、Discord 通知は無い。症状は uptime-check の外形監視ダウンとして間接的に検知される
- 90%到達は別の Cloud Function `budget-alert`（同じ `budget-alerts` Pub/Sub topic を独立サブスクリプションで購読、stop-billing のコード・IAMには変更なし）が Discord へ通知する（T143）。`costAmount / budgetAmount` を自前で計算し、GCS マーカーで月1回だけ通知する（dedup）。緩和措置は無い早期警告のみ
- 予算のコスト集計には数時間〜1日程度の遅延があるため、90%通知が届いた時点で実コストが既に90%を超えている可能性がある
- 対応手順は [RUNBOOK.md#f-課金遮断予算アラート](../RUNBOOK.md#f-課金遮断予算アラート)、仕組みの詳細は [infra/stop-billing/README.md](../../infra/stop-billing/README.md) / [infra/budget-alert/README.md](../../infra/budget-alert/README.md)

## 通知チャネル

- `infrastructure/notification_client.py` の `NotificationClient`。webhook 未設定なら自動で no-op
- 環境変数: `SLACK_WEBHOOK_URL` / `DISCORD_WEBHOOK_URL`（GitHub Actions は GitHub Secrets、GCP Cloud Run Jobs は Secret Manager。GCP 側は `DISCORD_WEBHOOK_URL` のみ登録）

## 補助スクリプト（`scripts/monitoring/`）

- `check_robots.py` — robots.txt 一括確認
- `health_check.sh` / `monitor.sh` — 手動ヘルスチェック
- `scripts/zero_count_audit.py` — 0 件サイトの監査
