# GitHub Actions ワークフロー一覧

`.github/workflows/` の全 11 本。時刻は cron（UTC）と JST 換算。

## 定期実行

| ワークフロー | トリガー | 内容 |
|---|---|---|
| `sns-publish.yml` | 毎日 `0 0 * * *`（JST 9:00）+ 手動（dry_run_override） | Threads 自動投稿（`python -m syndication_service.sns_publisher`）。`data/sns_posts.yaml` をコミット |
| `uptime-check.yml` | 30分毎 `*/30 * * * *` + 手動（force_failure） | Cloud Run `/health`・Vercel トップ・`/areas/東京都`（SSR サブルート）・収集鮮度（`last_collected_at`）を検証。3回リトライ。失敗時 Discord 通知 + CI failure |
| `secret-health.yml` | 毎日 `0 0 * * *`（JST 9:00）+ 手動 | Groq / Threads トークンの失効（401/403）を実呼び出しで検知 → Discord 通知。5xx/timeout は通知しない |

データ収集（旧 `data-collector.yml` のスケジュール実行）は 2026-08-14 に GCP Cloud Scheduler + Cloud Run Jobs（`oneco-collector`, `asia-northeast1`, 0:00 JST）へ移設した。理由: GitHub Actions ランナーの IP 帯が一部自治体サイトから累積アクセスペナルティを受け、収集が劣化・凍結したため（T048/T049）。

## 手動フォールバック

| ワークフロー | トリガー | 内容 |
|---|---|---|
| `data-collector.yml` | 手動のみ（`workflow_dispatch`） | GCP Cloud Run Jobs 側の定時収集が使えないときの代替実行。処理内容は GCP 版と同じ（alembic upgrade → `python -m data_collector` で 211 サイト収集 → `output/` `snapshots/` `data/*.yaml` を自動コミット。失敗時 Slack + Discord 通知。auto-fix の dispatch 元） |

## CI（push / PR）

| ワークフロー | トリガー | 内容 |
|---|---|---|
| `backend.yml` | push / PR → main（`src/**` `tests/**` `alembic/**` 等） | ruff check + **ruff format --check** + pytest（Python 3.11） |
| `frontend.yml` | push / PR → main（`frontend/**`） | ESLint + Vitest（+ Lighthouse / Playwright E2E ゲート、Node 20） |

## デプロイ

| ワークフロー | トリガー | 内容 |
|---|---|---|
| `deploy-backend.yml` | push → main（`src/**` `Dockerfile` `alembic/**` 等）+ 手動（run_migration トグル） | WIF キーレス認証 → Artifact Registry ビルド → Cloud Run `oneco-api`（asia-northeast1）デプロイ |
| `deploy-collector.yml` | push → main（`src/**` `Dockerfile.collector` `cloudbuild-collector.yaml` `scripts/collector_entrypoint.sh` 等）+ 手動 | WIF キーレス認証 → Artifact Registry ビルド → Cloud Run Jobs `oneco-collector`（asia-northeast1）の image / 環境変数を宣言的に更新（実行スケジュールは Cloud Scheduler が保持、ここはデプロイのみ） |
| （frontend） | Vercel の GitHub 連携 | `main` push で自動デプロイ（Actions 外） |

## ユーティリティ（手動 one-shot）

| ワークフロー | トリガー | 内容 |
|---|---|---|
| `sync-collector-secrets.yml` | 手動のみ（`workflow_dispatch`） | GitHub Actions secrets（`DATABASE_URL` / `GROQ_API_KEY` / `DISCORD_WEBHOOK_URL`）を GCP Secret Manager へ複製する。値を更新したときに再実行すれば新バージョンが追加される（Cloud Run Job は `:latest` を参照） |

## 自己修復（→ [詳細](04-self-healing.md)）

| ワークフロー | トリガー | 内容 |
|---|---|---|
| `auto-fix-adapter.yml` | 手動 dispatch のみ（site_name / model / dry_run）※通常は data-collector から自動 dispatch | Groq で adapter を修復、二重ガード通過で `auto-fix` ラベル付き PR 作成 |
| `auto-merge-fix-pr.yml` | PR イベント（opened / labeled 等） | `auto-fix` ラベル PR に CI green 後の squash auto-merge を設定 |

## 補足

- data-collector → auto-fix の dispatch には `ONECO_AUTO_FIX_TOKEN`（PAT）が必要。`GITHUB_TOKEN` では GitHub の recursion prevention により後続 workflow が発火しない
- 障害時の対応手順は [docs/RUNBOOK.md](../RUNBOOK.md)
