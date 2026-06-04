#!/bin/bash
# GCP Cloud Run デプロイセットアップスクリプト
set -euo pipefail

PROJECT_ID="oneco-app"
REGION="asia-northeast1"  # 東京
SERVICE_NAME="oneco-api"
REGISTRY="${REGION}-docker.pkg.dev/${PROJECT_ID}/oneco"
IMAGE="${REGISTRY}/api"

echo "=== [1/5] API有効化 ==="
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  --project="${PROJECT_ID}"

echo "=== [2/5] Artifact Registry 作成 ==="
gcloud artifacts repositories create oneco \
  --repository-format=docker \
  --location="${REGION}" \
  --description="oneco Docker images" \
  --project="${PROJECT_ID}" 2>/dev/null || echo "既存のリポジトリを使用"

echo "=== [3/5] Docker 認証設定 ==="
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

echo "=== [4/5] Docker ビルド & プッシュ ==="
cd "$(dirname "$0")/../.."
docker build -t "${IMAGE}:latest" .
docker push "${IMAGE}:latest"

echo "=== [4.5/5] 必須シークレット検証 ==="
# Cloud Run 起動前に必須環境変数を検証する。1つでも欠ければ即 exit 1。
# Codex リリースレビュー C-3: 'INTERNAL_API_TOKEN なしで Cloud Run が起動でき、
# 管理APIが匿名アクセス可能になる' 問題への対応。
required_vars=(
  "DATABASE_URL"          # Supabase 接続文字列
  "INTERNAL_API_TOKEN"    # 内部API 認証トークン (管理エンドポイント保護)
  "CORS_ORIGINS"          # 本番 frontend ドメイン
)
missing=()
for var in "${required_vars[@]}"; do
  if [ -z "${!var:-}" ]; then
    missing+=("${var}")
  fi
done
if [ ${#missing[@]} -gt 0 ]; then
  echo "ERROR: 必須環境変数が未設定です:"
  for var in "${missing[@]}"; do
    echo "  - ${var}"
  done
  echo ""
  echo "全ての変数を設定してから再実行してください。例:"
  echo "  export DATABASE_URL='postgresql+asyncpg://postgres:[PASSWORD]@db.[REF].supabase.co:5432/postgres'"
  echo "  export INTERNAL_API_TOKEN=\"\$(openssl rand -hex 32)\""
  echo "  export CORS_ORIGINS='https://oneco.example.com'"
  exit 1
fi

# CORS_ORIGINS=* は本番では危険なため拒否
if [ "${CORS_ORIGINS}" = "*" ]; then
  echo "ERROR: CORS_ORIGINS='*' は本番では許可されません。Vercel 本番ドメインを指定してください"
  exit 1
fi

echo "=== [4.8/5] DB マイグレーション (alembic upgrade head) ==="
# トラフィック切り替え前に必ず migration を完了させる。
# Codex リリースレビュー C-3: 'Alembic 手動実行でスキーマドリフト時に /admin/* が即死' への対応。
if ! command -v alembic >/dev/null 2>&1; then
  echo "ERROR: alembic がインストールされていません。pip install alembic を実行してください"
  exit 1
fi
echo "alembic upgrade head を実行中..."
DATABASE_URL="${DATABASE_URL}" alembic upgrade head

echo "=== [5/5] Cloud Run デプロイ ==="

gcloud run deploy "${SERVICE_NAME}" \
  --image="${IMAGE}:latest" \
  --region="${REGION}" \
  --platform=managed \
  --allow-unauthenticated \
  --port=8080 \
  --memory=512Mi \
  --cpu=1 \
  --min-instances=0 \
  --max-instances=3 \
  --set-env-vars="DATABASE_URL=${DATABASE_URL}" \
  --set-env-vars="INTERNAL_API_TOKEN=${INTERNAL_API_TOKEN}" \
  --set-env-vars="CORS_ORIGINS=${CORS_ORIGINS}" \
  --set-env-vars="LOG_LEVEL=INFO" \
  --project="${PROJECT_ID}"

echo ""
echo "=== デプロイ完了 ==="
SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --format="value(status.url)")
echo "API URL: ${SERVICE_URL}"
echo ""
echo "次のステップ:"
echo "  1. Vercel の環境変数に NEXT_PUBLIC_API_BASE_URL=${SERVICE_URL} を設定"
echo "  2. /health エンドポイントで疎通確認: curl ${SERVICE_URL}/health"
