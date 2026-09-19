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

echo "=== [4.7/5] Secret Manager へ認証情報を登録 (T425) ==="
# Cloud Run の環境変数は run.services.get 権限があれば誰でも平文で読めるため、
# DATABASE_URL と INTERNAL_API_TOKEN は Secret Manager 参照で渡す。
# 実行 SA には roles/secretmanager.secretAccessor (または上位ロール) が要る。
for secret_name in DATABASE_URL INTERNAL_API_TOKEN; do
  if ! gcloud secrets describe "${secret_name}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
    echo "Secret ${secret_name} を作成します"
    gcloud secrets create "${secret_name}" \
      --replication-policy=automatic \
      --project="${PROJECT_ID}"
  fi
  # 実行のたびに新しいバージョンが増える。古いバージョンは必要に応じて
  # gcloud secrets versions destroy で片付ける。
  printf '%s' "${!secret_name}" | gcloud secrets versions add "${secret_name}" \
    --data-file=- \
    --project="${PROJECT_ID}"
done

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
  --set-secrets="DATABASE_URL=DATABASE_URL:latest,INTERNAL_API_TOKEN=INTERNAL_API_TOKEN:latest" \
  --set-env-vars="^;^CORS_ORIGINS=${CORS_ORIGINS};LOG_LEVEL=INFO" \
  --project="${PROJECT_ID}"
# 注: 認証情報は --set-env-vars ではなく --set-secrets で渡す (T425)。Cloud Run の
#     env は run.services.get 権限があれば誰でも読めるため。
# 注: 先頭 "^;^" は区切り文字を ; に変更する gcloud 構文。CORS_ORIGINS がカンマ
#     区切りの複数 URL を持つため、既定のカンマ区切りだと dict パースが壊れる。
#     --set-env-vars を複数回渡すと後勝ちで上書きされるので 1 回にまとめる。

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
