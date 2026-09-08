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
