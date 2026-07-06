# 本番環境チェックリスト

本番構成（Cloud Run + Vercel + Supabase + GitHub Actions）を変更・再構築するときの確認項目。
デプロイの具体的手順は [DEPLOYMENT.md](DEPLOYMENT.md)、障害対応は [docs/RUNBOOK.md](docs/RUNBOOK.md)、全体像は [docs/wiki/](docs/wiki/README.md) を参照。

> 旧版はセルフホスト (docker-compose) 前提の汎用テンプレートだったため、2026-07-06 に実構成に合わせて全面書き換え。

## 1. インフラ

- [ ] **Supabase PostgreSQL**
  - [ ] `DATABASE_URL` は **transaction-mode プーラー (:6543)** を使う（session :5432 は EMAXCONNSESSION 枯渇の教訓により禁止。PR #233）
  - [ ] anon ロールの権限剥奪が維持されている（RLS + REVOKE 系マイグレーション適用済みか）
  - [ ] バックアップ（Supabase 自動バックアップ）有効
- [ ] **Cloud Run** (`oneco-api`, asia-northeast1)
  - [ ] `deploy-backend.yml` の WIF（Workload Identity Federation）が有効。SA キーの JSON は使わない
  - [ ] **min instances は 0 のまま**（上げるとコスト発生。無料枠内運用が方針）
  - [ ] Artifact Registry の古いイメージを定期削除（6GB 超で実費発生の実績あり）
- [ ] **Vercel**（frontend）
  - [ ] `main` push の自動デプロイが有効
  - [ ] `NEXT_PUBLIC_API_BASE_URL` が Cloud Run URL を指している
- [ ] **Redis**: 任意（不在でも動作する。PR #160）。契約不要

## 2. Secrets / 環境変数

- [ ] **GitHub Actions Secrets**: `DATABASE_URL` / `GROQ_API_KEY` / `INTERNAL_API_TOKEN` / `SLACK_WEBHOOK_URL` / `DISCORD_WEBHOOK_URL` / Threads 系 / `ONECO_AUTO_FIX_TOKEN`(PAT)
- [ ] **Repo Variables**（段階リリーストグル）: `THREADS_PUBLISH_ENABLED` / `THREADS_PUBLISH_DRY_RUN` / auto-fix 系
- [ ] `INTERNAL_API_TOKEN` は `openssl rand -hex 32` で生成
- [ ] ローカルの保管は Keychain（`oneco-*` プレフィックス）または `.env`（gitignore 済み）。shell rc への直書き禁止
- [ ] ローテーション後は `deploy-backend.yml` を手動実行して Cloud Run に反映（Secrets 変更だけでは反映されない）

## 3. デプロイ後の確認

- [ ] `curl https://<cloud-run-url>/health` → 200
- [ ] frontend トップ + `/areas/東京都`（SSR サブルート）→ 200
- [ ] `gh run list` で `uptime-check.yml` の直近 run が green
- [ ] Cloud Run ログにエラーがないこと（デプロイ後 10 分程度）
- [ ] データ収集の翌日 run が成功し、`Update collection data [automated]` コミットが積まれること

## 4. 監視が生きていることの確認

- [ ] `uptime-check.yml`（30分毎）が有効
- [ ] `secret-health.yml`（日次）が有効
- [ ] Discord/Slack webhook が生きている（`workflow_dispatch(force_failure)` でテスト可能）

## 5. 未公開機能（配線しないこと）

- LINE 通知（`notification_manager`）は実装済みだが未配線。`LINE_CHANNEL_*` の設定は不要
- 公開 API の rate limit は SSR exempt 設計が整うまで意図的に未導入
