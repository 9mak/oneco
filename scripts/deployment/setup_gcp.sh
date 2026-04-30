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

echo "=== [5/5] Cloud Run デプロイ ==="
# DATABASE_URL は Supabase の接続文字列に差し替えてください
if [ -z "${DATABASE_URL:-}" ]; then
  echo "ERROR: DATABASE_URL が未設定です"
  echo "Supabase の接続文字列を設定してから再実行してください:"
  echo "  export DATABASE_URL='postgresql+asyncpg://postgres:[PASSWORD]@db.[REF].supabase.co:5432/postgres'"
  exit 1
fi

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
  --set-env-vars="CORS_ORIGINS=${CORS_ORIGINS:-*}" \
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
echo "  2. alembic マイグレーション実行:"
echo "     DATABASE_URL='${DATABASE_URL}' python3 -m alembic upgrade head"
