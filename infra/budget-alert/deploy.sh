#!/usr/bin/env bash
# budget-alert のデプロイスクリプト。
#
# 前提:
# - stop-billing (infra/stop-billing) には一切触らない。同じ Pub/Sub topic
#   (budget-alerts) を独立したサブスクリプションで購読するだけ。
# - 権限は最小: マーカー用GCSバケットへの objectCreator/objectViewer と、
#   DISCORD_WEBHOOK_URL secretへの secretAccessor のみ。roles/billing.* は
#   一切付与しない（課金操作をこのFunctionにやらせないための境界）。
#
# 使い方:
#   ./deploy.sh --dry-run                 # 実行されるコマンドを表示するだけ
#   ./deploy.sh                            # 実際にデプロイ
#
# 環境変数（上書き可）:
#   GCP_PROJECT_ID          (既定: oneco-app)
#   GCP_REGION               (既定: asia-northeast1)
#   BUDGET_ALERT_BUCKET      (既定: ${GCP_PROJECT_ID}-budget-alert-markers)
#   BUDGET_ALERT_SA          (既定: oneco-budget-alert@${GCP_PROJECT_ID}.iam.gserviceaccount.com)
#   DISCORD_SECRET_NAME      (既定: DISCORD_WEBHOOK_URL、stop-billingが使っているものと同じsecretを再利用)

set -euo pipefail

DRY_RUN=false
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    *)
      echo "unknown arg: $arg" >&2
      exit 1
      ;;
  esac
done

PROJECT_ID="${GCP_PROJECT_ID:-oneco-app}"
REGION="${GCP_REGION:-asia-northeast1}"
BUCKET="${BUDGET_ALERT_BUCKET:-${PROJECT_ID}-budget-alert-markers}"
SA_NAME="oneco-budget-alert"
SA_EMAIL="${BUDGET_ALERT_SA:-${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com}"
SECRET_NAME="${DISCORD_SECRET_NAME:-DISCORD_WEBHOOK_URL}"
FUNCTION_NAME="budget-alert"

run() {
  echo "+ $*"
  if [ "$DRY_RUN" = false ]; then
    "$@"
  fi
}

echo "=== budget-alert デプロイ計画 ==="
echo "project=${PROJECT_ID} region=${REGION} bucket=${BUCKET} sa=${SA_EMAIL} secret=${SECRET_NAME}"
echo "dry_run=${DRY_RUN}"
echo

echo "--- 1. マーカー用GCSバケット（存在しなければ作成、idempotent） ---"
if gcloud storage buckets describe "gs://${BUCKET}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  echo "既存: gs://${BUCKET}（作成スキップ）"
else
  run gcloud storage buckets create "gs://${BUCKET}" \
    --project="${PROJECT_ID}" --location="${REGION}" \
    --uniform-bucket-level-access
fi

echo
echo "--- 2. 専用サービスアカウント（存在しなければ作成、idempotent） ---"
if gcloud iam service-accounts describe "${SA_EMAIL}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  echo "既存: ${SA_EMAIL}（作成スキップ）"
else
  run gcloud iam service-accounts create "${SA_NAME}" \
    --project="${PROJECT_ID}" \
    --display-name="budget-alert Cloud Function (T143)"
fi

echo
echo "--- 3. IAM: バケットへ objectCreator/objectViewer のみ（billing系権限は付与しない） ---"
run gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
  --project="${PROJECT_ID}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/storage.objectCreator"
run gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
  --project="${PROJECT_ID}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/storage.objectViewer"

echo
echo "--- 4. IAM: Discord webhook secretへの secretAccessor のみ ---"
run gcloud secrets add-iam-policy-binding "${SECRET_NAME}" \
  --project="${PROJECT_ID}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/secretmanager.secretAccessor"

echo
echo "--- 5. Cloud Function デプロイ（gen2, budget-alerts topicを独立サブスクリプションで購読） ---"
run gcloud functions deploy "${FUNCTION_NAME}" \
  --gen2 --project="${PROJECT_ID}" --region="${REGION}" \
  --runtime=python312 --trigger-topic=budget-alerts \
  --entry-point=budget_alert --source=infra/budget-alert \
  --run-service-account="${SA_EMAIL}" \
  --set-secrets="DISCORD_WEBHOOK_URL=${SECRET_NAME}:latest" \
  --set-env-vars="BUDGET_ALERT_BUCKET=${BUCKET}" \
  --memory=256Mi --cpu=1 --max-instances=3 --no-allow-unauthenticated

echo
echo "=== 完了 ==="
echo "stop-billing (infra/stop-billing) には一切変更を加えていません。"
echo
echo "検証手順は README.md の「テスト手順」を参照。"
echo "  ★ 本番topicへは costAmount < budgetAmount のメッセージのみ publish すること"
echo "    （costAmount >= budgetAmount は stop-billing が実際に課金解除してしまう）。"
