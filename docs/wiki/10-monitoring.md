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
              └ auto-fix dispatch 失敗    → WARNING

Workflow 失敗  各 workflow の「Notify Discord on failure」ステップ

課金アラート   GCP 予算 (oneco-monthly-cap-500, ¥500/月) を budget-alerts topic 経由で
              2つの Cloud Function が独立購読
              ├ 90% 到達  → budget-alert が Discord 通知（早期警告、緩和措置なし）
              └ 100% 到達 → stop-billing が課金解除（メール通知のみ、Discord 無し。→ RUNBOOK F 節）

GA4 週次読上   ga4-weekly.yml (毎週月曜 JST9:10)
              ユーザー数・動物詳細PV・external_link_click の前週比を Discord へ通知
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

### GA4 週次読上（`ga4-weekly.yml` → `scripts/ga4_weekly_report.py`）

- GA4 property `properties/541319394`（oneco, G-KEE66C1E8B）から直近7日 (JST 前日締め) と
  前週7日を取得し、増減つきの Markdown レポート (workflow artifact, 400日保持) を出力する
- Discord へはユーザー数 / 動物詳細ページ (`/animals/*`) 閲覧数 / `external_link_click` の
  3指標のみ前週比つきで通知（詳細はレポート artifact 側）
- 認証は WIF。GA4 閲覧専用サービスアカウント `oneco-ga4-mcp@oneco-app.iam.gserviceaccount.com`
  を使う（deploy 用 SA とは別。roles: Viewer on GA4 property）
- GA4 API 障害時はサイレントに成功終了せず、Discord へ失敗を通知した上で workflow も
  failure にする（secret-health.yml と同じ二重ガード）
- `--dry-run` でローカル確認可能（Discord 送信せず標準出力に表示）

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
