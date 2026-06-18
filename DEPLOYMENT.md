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

`deploy-backend.yml` が push デプロイ時に `alembic upgrade head` を自動適用する。ローカルから手動で実行する場合：

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

| 変数名 | 説明 |
|--------|------|
| `NEXT_PUBLIC_API_BASE_URL` | Backend API のベース URL（例: `https://oneco-api-tvlsrcvyuq-an.a.run.app`） |
| `NEXT_PUBLIC_SITE_URL` | 本番サイトの URL（canonical / sitemap / OGP に使用。未設定だと本番ビルドが失敗するガードあり） |

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
| `GROQ_API_KEY` | Groq API キー（デフォルト LLM プロバイダ。抽出セレクタ生成等に使用） | ✅ |
| `ANTHROPIC_API_KEY` | Claude API キー（フォールバック LLM プロバイダ） | - |
| `SLACK_WEBHOOK_URL` | 収集結果通知用 Slack Webhook | - |

### 収集失敗の対処

1. **Groq レート制限/クォータ超過**: 時間をおいて再実行で解消（必要なら `ANTHROPIC_API_KEY` を設定してフォールバック）。
2. **ネットワークタイムアウト**: 外部自治体サイトの問題。数日中に自動回復。
3. **DB 保存失敗**: GitHub Actions のログで `Failed to save animal to database:` の後のエラー内容を確認。

---

## CI/CD パイプライン

```
git push → GitHub Actions
               │
               ├─ backend.yml        ─▶ Lint → Test → Build
               ├─ deploy-backend.yml ─▶ alembic → Cloud Build → Cloud Run デプロイ（自動）
               ├─ frontend.yml       ─▶ Lint → Test → Vercel デプロイ（自動）
               └─ data-collector.yml（スケジュール）─▶ データ収集
```

Backend（Cloud Run）は `deploy-backend.yml` により `main` への push で自動デプロイされる（`src/`・`Dockerfile`・`requirements.txt`・`pyproject.toml`・`alembic/` 変更時）。WIF でキーレス認証し、push 時は `alembic upgrade head` も自動適用される。手動デプロイは `workflow_dispatch`（`run_migration` トグルあり）または上記の `gcloud run deploy` で可能。

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
