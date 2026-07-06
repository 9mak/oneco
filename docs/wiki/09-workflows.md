# GitHub Actions ワークフロー一覧

`.github/workflows/` の全 9 本。時刻は cron（UTC）と JST 換算。

## 定期実行

| ワークフロー | トリガー | 内容 |
|---|---|---|
| `data-collector.yml` | 毎日 `0 15 * * *`（JST 0:00）+ 手動 | alembic upgrade → `python -m data_collector` で 211 サイト収集 → `output/` `snapshots/` `data/*.yaml` を自動コミット。失敗時 Slack + Discord 通知。auto-fix の dispatch 元 |
| `sns-publish.yml` | 毎日 `0 0 * * *`（JST 9:00）+ 手動（dry_run_override） | Threads 自動投稿（`python -m syndication_service.sns_publisher`）。`data/sns_posts.yaml` をコミット |
| `uptime-check.yml` | 30分毎 `*/30 * * * *` + 手動（force_failure） | Cloud Run `/health`・Vercel トップ・`/areas/東京都`（SSR サブルート）を HTTP 200 検証。3回リトライ。失敗時 Discord 通知 + CI failure |
| `secret-health.yml` | 毎日 `0 0 * * *`（JST 9:00）+ 手動 | Groq / Threads トークンの失効（401/403）を実呼び出しで検知 → Discord 通知。5xx/timeout は通知しない |

## CI（push / PR）

| ワークフロー | トリガー | 内容 |
|---|---|---|
| `backend.yml` | push / PR → main（`src/**` `tests/**` `alembic/**` 等） | ruff check + **ruff format --check** + pytest（Python 3.11） |
| `frontend.yml` | push / PR → main（`frontend/**`） | ESLint + Vitest（+ Lighthouse / Playwright E2E ゲート、Node 20） |

## デプロイ

| ワークフロー | トリガー | 内容 |
|---|---|---|
| `deploy-backend.yml` | push → main（`src/**` `Dockerfile` `alembic/**` 等）+ 手動（run_migration トグル） | WIF キーレス認証 → Artifact Registry ビルド → Cloud Run `oneco-api`（asia-northeast1）デプロイ |
| （frontend） | Vercel の GitHub 連携 | `main` push で自動デプロイ（Actions 外） |

## 自己修復（→ [詳細](04-self-healing.md)）

| ワークフロー | トリガー | 内容 |
|---|---|---|
| `auto-fix-adapter.yml` | 手動 dispatch のみ（site_name / model / dry_run）※通常は data-collector から自動 dispatch | Groq で adapter を修復、二重ガード通過で `auto-fix` ラベル付き PR 作成 |
| `auto-merge-fix-pr.yml` | PR イベント（opened / labeled 等） | `auto-fix` ラベル PR に CI green 後の squash auto-merge を設定 |

## 補足

- data-collector → auto-fix の dispatch には `ONECO_AUTO_FIX_TOKEN`（PAT）が必要。`GITHUB_TOKEN` では GitHub の recursion prevention により後続 workflow が発火しない
- 障害時の対応手順は [docs/RUNBOOK.md](../RUNBOOK.md)
