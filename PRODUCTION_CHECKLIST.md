# 本番環境リリースチェックリスト

一般公開リリース前に確認・実施すべき項目。手順の詳細は [DEPLOYMENT.md](./DEPLOYMENT.md) を参照。

## 構成（現行）

| レイヤー | 実体 |
|---|---|
| Backend API | FastAPI（`data_collector` + `syndication_service`）を **Cloud Run** にデプロイ |
| Database | **Supabase** PostgreSQL |
| Frontend | Next.js を **Vercel** にデプロイ（Git 連携で自動デプロイ） |
| データ収集 | **GitHub Actions** の cron（毎日 JST 00:00、`data-collector.yml`）。結果は DB に保存し、frontend は API 経由で取得 |
| アラート | **Slack** Webhook（収集失敗・欠損ドリフト通知） |
| 自己修復 | `auto-fix-adapter.yml`（現状 `workflow_dispatch` 手動トリガー） |

> 注: 旧 docker-compose / nginx / LINE 通知 / S3 バックアップ構成は廃止済み。このチェックリストは Cloud Run + Supabase + Vercel 構成に対応する。

---

## 🚦 リリースブロッカー（公開前に必須）

これらが未対応だと「公開したらフロントが真っ白／API が全滅」になる。リリース前監査（2026-06-02）で特定。

- [ ] **Backend を Cloud Run に実デプロイ**（自動デプロイ workflow は未整備＝手動 `gcloud run deploy`。frontend だけ公開すると全 API が落ちる）
- [ ] **Supabase に `alembic upgrade head` 適用済み**（未適用だと `/health` の `SELECT 1` が落ち全 API が 503。Cloud Run に自動適用の仕組みは無い）
- [ ] **Cloud Run に `CORS_ORIGINS=https://<Vercel本番ドメイン>` を設定**（未設定だと本番フロントの fetch が CORS で全ブロック。`*` は動くが非推奨）
- [ ] **Vercel に `NEXT_PUBLIC_API_BASE_URL=https://<Cloud Run URL>` を設定**（未設定だと `http://localhost:8000` にフォールバックし「Failed to fetch animals」。`NEXT_PUBLIC_*` はビルド時インラインなので**設定後に再デプロイ**）
- [ ] **Vercel に `NEXT_PUBLIC_SITE_URL=https://<本番ドメイン>` を設定**（未設定だと sitemap/robots/OGP/canonical が localhost を指し SEO・SNS 共有が壊れる）
- [ ] **GitHub Secrets を実変数名で登録**（`DATABASE_URL` ✅必須／`SLACK_WEBHOOK_URL` 推奨／`GROQ_API_KEY` は自己修復用で任意。**Gemini/`GOOGLE_API_KEY` は不使用**）

---

## 1. インフラ準備

- [ ] GCP プロジェクト・Artifact Registry リポジトリ作成済み（`gcloud` 認証済み）
- [ ] Supabase プロジェクト作成、PostgreSQL 接続文字列を取得（`postgresql+asyncpg://...`）
- [ ] Supabase の自動バックアップ設定を確認（PITR / 日次バックアップ）
- [ ] Vercel プロジェクト作成、GitHub リポジトリと連携
- [ ] 独自ドメイン利用時: DNS / SSL（Vercel・Cloud Run 側で自動）

## 2. 環境変数・シークレット

### Cloud Run（Backend）
- [ ] `DATABASE_URL`（Supabase 接続。**必須**）
- [ ] `CORS_ORIGINS`（Vercel 本番ドメイン。**必須**）
- [ ] `INTERNAL_API_TOKEN`（`openssl rand -hex 32`。PATCH/admin 認証。**必須**。Vercel 側と同一値）
- [ ] `LOG_LEVEL`（`INFO` 等）
- [ ] `REDIS_URL`（任意。未設定だと slowapi レート制限は **fail-open で無効化**される。公開 GET 中心なら許容だが DoS 耐性のため Memorystore 等を推奨）

### Vercel（Frontend）
- [ ] `NEXT_PUBLIC_API_BASE_URL`（Cloud Run URL。**必須**）
- [ ] `NEXT_PUBLIC_SITE_URL`（本番ドメイン。**必須**）
- [ ] 管理画面 `/admin/*` を使う場合: `BACKEND_INTERNAL_URL` / `INTERNAL_API_TOKEN` / `ADMIN_GITHUB_LOGIN` / `AUTH_SECRET` / `AUTH_GITHUB_ID` / `AUTH_GITHUB_SECRET`（GitHub OAuth App を作成）

### GitHub Actions Secrets（データ収集）
- [ ] `DATABASE_URL`（**必須**）
- [ ] `SLACK_WEBHOOK_URL`（推奨。未設定だと失敗通知が**無音でスキップ**され気づけない）
- [ ] `GROQ_API_KEY`（任意。アダプター自己修復で使用。通常収集は rule-based 100%）

### シークレット衛生
- [ ] `.env` / `.env.production` をコミットしていない（`.gitignore` 済み確認）
- [ ] トークンは Cloud Run / Vercel / GitHub の各 Secret 機能で管理（rc ファイル直書き禁止）

## 3. データベース

- [ ] `DATABASE_URL=... alembic upgrade head` を Supabase に対して実行
- [ ] `alembic current` で最新リビジョン確認
- [ ] Supabase Table Editor で `animals` テーブル存在＆件数確認

## 4. デプロイ実行

- [ ] Backend: `gcloud builds submit --tag <IMAGE> .` → `gcloud run deploy oneco-api --image <IMAGE> --region asia-northeast1 --allow-unauthenticated --set-env-vars ...`（[DEPLOYMENT.md](./DEPLOYMENT.md) 参照）
- [ ] Frontend: main への push で Vercel が自動デプロイ（環境変数設定後に再デプロイ）
- [ ] 未マージの release 用 PR を取り込み済みか確認（フィールド抽出 fix・PII フィルタ・経過日数バッジ等）

## 5. 動作確認（デプロイ後30分以内）

- [ ] `curl https://<Cloud Run>/health` → `{"status":"healthy",...}`
- [ ] `curl "https://<Cloud Run>/animals?limit=10"` → 動物データが返る
- [ ] OpenAPI: `https://<Cloud Run>/docs` が表示される
- [ ] RSS/Atom フィード（syndication_service）が取得できる
- [ ] 本番フロント（Vercel）トップで動物一覧が表示される（「Failed to fetch」が出ない＝#1〜#4 が正しい証拠）
- [ ] 動物詳細ページで「元のページを見る」リンク・連絡先・経過日数バッジが表示される
- [ ] `/privacy` `/terms` `/robots.txt` `/sitemap.xml` が本番ドメインで正しく出る（localhost が混入していない）
- [ ] OGP: 動物詳細 URL を SNS/Slack に貼り、カード画像が出る
- [ ] `/admin/*` が未ログインで `/admin/signin` にリダイレクトされる（公開保護の確認）

## 6. 監視・運用

- [ ] Slack に収集サマリ／失敗通知が届く（`SLACK_WEBHOOK_URL` 設定後、手動 `gh workflow run "Data Collector"` でテスト）
- [ ] Cloud Run のログ／エラーアラート（Cloud Monitoring）を設定
- [ ] 翌日: GitHub Actions の収集 cron が成功し DB が更新されたか確認
- [ ] 欠損ドリフト検知（`field_quality_drift.yaml`）と broken_sites 監視が動作

## 7. ロールバック

- [ ] Backend: `gcloud run services update-traffic oneco-api --to-revisions <PREV>=100`
- [ ] Frontend: Vercel ダッシュボードで前デプロイへ即時ロールバック
- [ ] DB マイグレーション: `alembic downgrade -1`（破壊的変更は事前にバックアップ）

## 🚨 トラブルシューティング

- **フロントが「Failed to fetch animals」**: Vercel の `NEXT_PUBLIC_API_BASE_URL` 未設定/誤り、または Cloud Run の `CORS_ORIGINS` にフロントドメイン未登録。設定後フロントを再デプロイ。
- **API が全部 503**: `alembic upgrade head` 未適用、または `DATABASE_URL` 誤り（`/health` が DB 依存）。
- **管理画面に入れない**: `ADMIN_GITHUB_LOGIN` / `AUTH_SECRET` / `AUTH_GITHUB_ID/SECRET` 未設定、または GitHub OAuth App のコールバック URL 不一致。
- **収集失敗に気づけない**: `SLACK_WEBHOOK_URL` 未設定（無音スキップ）。
- **OGP/SEO が localhost**: `NEXT_PUBLIC_SITE_URL` 未設定。

## 📚 参考

- [DEPLOYMENT.md](./DEPLOYMENT.md) - デプロイ手順詳細
- [README.md](./README.md) - プロジェクト概要

---

**最終更新**: 2026-06-02（Cloud Run + Supabase + Vercel 構成へ全面改訂。旧 docker-compose 版を破棄）
