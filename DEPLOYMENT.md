# 本番環境デプロイガイド

実際の本番環境は **Google Cloud Run + Vercel + Supabase** 構成です。

## 構成概要

| コンポーネント | サービス | リージョン |
|-------------|---------|---------|
| Backend API | Google Cloud Run | `asia-northeast1`（東京） |
| Container Registry | Artifact Registry | `asia-northeast1` |
| Database | Supabase PostgreSQL | `aws-1-ap-northeast-2` |
| Frontend | Vercel | 自動（CDN） |
| Data Collector | GitHub Actions | - |

---

## Backend デプロイ（Cloud Run）

### 前提条件

- `gcloud` CLI インストール・認証済み
- GCP プロジェクト設定済み
- Artifact Registry リポジトリ作成済み

### 手順

```bash
# 1. Docker イメージをビルドして Artifact Registry にプッシュ
PROJECT_ID="your-gcp-project-id"
REGION="asia-northeast1"
IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/oneco/oneco-api"

gcloud builds submit --tag $IMAGE .

# 2. Cloud Run にデプロイ
gcloud run deploy oneco-api \
  --image $IMAGE \
  --region $REGION \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars DATABASE_URL="postgresql+asyncpg://...",CORS_ORIGINS="*",LOG_LEVEL="INFO"
```

### 環境変数

Cloud Run の環境変数として設定する：

| 変数名 | 説明 | 例 |
|--------|------|---|
| `DATABASE_URL` | Supabase 接続 URL | `postgresql+asyncpg://postgres.<project>:<pass>@aws-1-ap-northeast-2.pooler.supabase.com:5432/postgres` |
| `CORS_ORIGINS` | 許可 CORS オリジン（カンマ区切り、本番ドメイン明示推奨） | `https://your-frontend.vercel.app` |
| `LOG_LEVEL` | ログレベル | `INFO` |
| `INTERNAL_API_TOKEN` | **必須**: PATCH /animals/{id}/status 等の内部 API 認証トークン。`openssl rand -hex 32` で生成し Secret Manager 推奨 | `<32-byte hex>` |

### ヘルスチェック

```bash
curl https://oneco-api-tvlsrcvyuq-an.a.run.app/health
# {"status":"healthy","timestamp":"..."}
```

### データベースマイグレーション

Cloud Run にデプロイ後、マイグレーションは手動実行：

```bash
# ローカルから Supabase に対して実行
DATABASE_URL="postgresql+asyncpg://..." alembic upgrade head
```

---

## Frontend デプロイ（Vercel）

### 自動デプロイ

`main` ブランチへの push で Vercel が自動デプロイします。GitHub Actions の `frontend.yml` がテストを通過後、Vercel の GitHub 連携が発火します。

### 手動デプロイ（初期設定・緊急時）

```bash
cd frontend
npm install -g vercel
vercel --prod
```

### 環境変数（Vercel ダッシュボードで設定）

`NEXT_PUBLIC_*` は**ビルド時にバンドルへインライン**されるため、設定後は再デプロイが必要。

| 変数名 | 説明 | 必須 |
|--------|------|------|
| `NEXT_PUBLIC_API_BASE_URL` | Backend API（Cloud Run）の公開 URL。**未設定だと `http://localhost:8000` にフォールバックし、公開フロントが API に繋がらず「Failed to fetch animals」になる** | ✅ |
| `NEXT_PUBLIC_SITE_URL` | 本番フロントの公開 URL（例 `https://oneco.vercel.app`）。sitemap.xml / robots.txt / OGP / canonical に使用。**未設定だと `http://localhost:3000` にフォールバックし SEO・SNS 共有が壊れる** | ✅ |
| `BACKEND_INTERNAL_URL` | 管理画面（サーバー側）から backend を叩く URL。通常 `NEXT_PUBLIC_API_BASE_URL` と同値 | 管理画面利用時 |
| `INTERNAL_API_TOKEN` | 管理画面の内部 API 呼び出し用トークン。**Cloud Run 側と同一値**を設定 | 管理画面利用時 |
| `ADMIN_GITHUB_LOGIN` | 管理画面へのアクセスを許可する GitHub ログイン名（これ未設定だと全員ログイン不可） | 管理画面利用時 |
| `AUTH_SECRET` | NextAuth セッション暗号化シークレット（`openssl rand -hex 32` で生成） | 管理画面利用時 |
| `AUTH_GITHUB_ID` | GitHub OAuth App の Client ID | 管理画面利用時 |
| `AUTH_GITHUB_SECRET` | GitHub OAuth App の Client Secret | 管理画面利用時 |

> 注: 公開閲覧側は上記のうち `NEXT_PUBLIC_API_BASE_URL` / `NEXT_PUBLIC_SITE_URL` のみで動作する。`INTERNAL_API_TOKEN` 以下は `/admin/*`（サイト健全性ダッシュボード）を使う場合のみ必要。

---

## Database（Supabase）

### マイグレーション適用

```bash
# alembic で直接 Supabase に適用
DATABASE_URL="postgresql+asyncpg://<接続文字列>" alembic upgrade head

# 適用済みバージョン確認
DATABASE_URL="postgresql+asyncpg://<接続文字列>" alembic current
```

### 接続確認

Supabase ダッシュボード → Table Editor → `animals` テーブルでデータを確認。

---

## Data Collector（GitHub Actions）

### 自動実行

毎日 JST 00:00 に `.github/workflows/data-collector.yml` が自動実行されます。

### 手動実行

```bash
# GitHub CLI から手動トリガー（workflow_dispatch 権限が必要）
gh workflow run "Data Collector" --ref main
```

### 必要な GitHub Secrets

GitHub リポジトリの Settings → Secrets and variables → Actions で設定：

| Secret 名 | 説明 | 必須 |
|-----------|------|------|
| `DATABASE_URL` | Supabase PostgreSQL 接続 URL | ✅ |
| `GROQ_API_KEY` | アダプター自己修復（auto-fix-adapter）用 Groq API キー。収集自体は rule-based 100% で動くため通常収集には不要 | - |
| `ANTHROPIC_API_KEY` | （未使用。LLM プロバイダは Groq に一本化済み。後方互換でワークフローが参照するのみ） | - |
| `SLACK_WEBHOOK_URL` | 収集結果・失敗通知用 Slack Webhook。**未設定だと通知が無音でスキップされ、収集失敗に気づけない**ため本番では設定推奨 | - |

### 収集失敗の対処

1. **Groq クォータ超過（自己修復実行時）**: レート上限到達時は時間をおいて再実行。通常収集は rule-based のため影響なし。
2. **ネットワークタイムアウト**: 外部自治体サイトの問題。数日中に自動回復。
3. **DB 保存失敗**: GitHub Actions のログで `Failed to save animal to database:` の後のエラー内容を確認。

---

## CI/CD パイプライン

```
git push → GitHub Actions
               │
               ├─ backend.yml  ─▶ Lint → Test → Build
               ├─ frontend.yml ─▶ Lint → Test → Vercel デプロイ（自動）
               └─ data-collector.yml（スケジュール）─▶ データ収集
```

Backend（Cloud Run）への自動デプロイは未設定。手動で `gcloud run deploy` を実行する。

---

## ロールバック

### Backend（Cloud Run）

```bash
# 前リビジョンに 100% トラフィックを戻す
gcloud run services update-traffic oneco-api \
  --region asia-northeast1 \
  --to-revisions oneco-api-00004-j9g=100
```

### Frontend（Vercel）

Vercel ダッシュボード → Deployments → 旧デプロイの「Promote to Production」

---

## 監視・確認

```bash
# Cloud Run ステータス
gcloud run services describe oneco-api --region asia-northeast1

# 最新リビジョン一覧
gcloud run revisions list --service oneco-api --region asia-northeast1

# GitHub Actions 直近の実行
gh run list --limit 10

# API ヘルスチェック
curl https://oneco-api-tvlsrcvyuq-an.a.run.app/health
```
