#!/bin/bash
# oneco-collector (Cloud Run Job) 実行失敗アラートのセットアップ
#
# 背景 (T109・2026-08):
#   Cloud Run Jobs (oneco-collector, asia-northeast1) には GCP Monitoring の
#   アラートポリシーが1件も無い (alertPolicies が空)。OOM・非ゼロ終了・
#   taskTimeout超過はすべて現状無音で、唯一のバックストップは
#   .github/workflows/uptime-check.yml の26時間 freshness チェック
#   (last_collected_at 経由・検知まで最大26h遅延) だけだった。
#
# このスクリプトが作るもの:
#   1. 通知チャンネル (Email, type=email) — 未作成なら1件作成、既存なら再利用
#   2. アラートポリシー (policies/job-execution-failed.json) — 2条件を OR:
#      - 実行失敗 (result != succeeded): OOM・非ゼロ終了・taskTimeout超過を
#        まとめて捕捉する。Cloud Run Jobs は taskCount=1 の単一タスク構成の
#        ため、タスクの失敗理由を問わず実行(execution)全体が result=failed
#        として記録される。ログベースメトリクスを個別に作る必要はない。
#      - 実行記録なし (25h absence): Scheduler が起動できなかった等、
#        「実行自体が始まらない」無音死を捕捉する。26h freshness チェックより
#        1時間早く、かつ「実行記録がない」という具体的な一次診断ヒント付きで
#        鳴らす (freshness チェックは残し、二重の安全網として維持する)。
#
# 閾値の根拠 (独断で決めず保守的なデフォルトを選ぶ):
#   - 実行失敗は「1回でも失敗したら即通知」(閾値=1, duration=0s)。
#     collector は1日1回・max-retries=0 で自動リトライが無いため、1回の
#     失敗がその日の収集を丸ごと失う。broken_sites.yaml の個別サイト向け
#     consecutive_failures=3 と同じ「連続N回まで待つ」設計は、収集全体の
#     欠落を最大3日放置することになり過大にリスキーなため採用しない。
#   - 実行記録なしは 25時間 (通常は0:00 JSTに1日1回起動されるため、
#     Scheduler のジッター込みでも24hを大きく超えて記録が無ければ異常)。
#
# 前提:
#   - gcloud CLI が認証済みで、対象プロジェクトへの
#     roles/monitoring.editor (または同等) 権限を持つこと
#   - 通知チャンネル作成には `gcloud beta monitoring channels` (beta
#     コンポーネント) を使う。未インストールの場合は
#     `gcloud components install beta` で追加する (ローカル CLI への
#     追加のみで GCP 側には影響しない)
#
# Usage:
#   ALERT_EMAIL='you@example.com' ./infra/collector-alerts/setup_alerts.sh
#   DRY_RUN=true ALERT_EMAIL='you@example.com' ./infra/collector-alerts/setup_alerts.sh  # コマンドを表示するだけで実行しない
#
# 環境変数:
#   ALERT_EMAIL   : (必須) 通知先メールアドレス
#   GCP_PROJECT_ID: デフォルト oneco-app
#   JOB_NAME      : デフォルト oneco-collector
#   DRY_RUN       : true にすると作成系コマンドを実行せず表示のみ行う (デフォルト false)
#
# 注意:
#   - このスクリプトは PR マージ後に手動実行することを想定している
#     (T109 のスコープは「コード化してPRにする」まで。本番適用は別途 HIL)。
#   - 同名の通知チャンネル/ポリシーが既に存在する場合は重複作成せず再利用
#     (チャンネル) または中断する (ポリシー。更新は `gcloud monitoring
#     policies update` を使うこと)。

set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-oneco-app}"
JOB_NAME="${JOB_NAME:-oneco-collector}"
ALERT_EMAIL="${ALERT_EMAIL:?ALERT_EMAIL に通知先メールアドレスを指定してください (例: ALERT_EMAIL='you@example.com' ./setup_alerts.sh)}"
DRY_RUN="${DRY_RUN:-false}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POLICY_FILE="${SCRIPT_DIR}/policies/job-execution-failed.json"

CHANNEL_DISPLAY_NAME="oneco-collector 実行失敗通知 (Email)"
POLICY_DISPLAY_NAME="oneco-collector 実行失敗 / 実行記録なし"

if [ ! -f "$POLICY_FILE" ]; then
  echo "ポリシー定義ファイルが見つかりません: $POLICY_FILE" >&2
  exit 1
fi

echo "[INFO] project=${PROJECT_ID} job=${JOB_NAME} email=${ALERT_EMAIL} dry_run=${DRY_RUN}"

# --- 1. 通知チャンネル (Email) ---
# 既存チャンネルの検索は read-only なので DRY_RUN でも常に実行する
EXISTING_CHANNEL="$(gcloud beta monitoring channels list \
  --project="$PROJECT_ID" \
  --filter="displayName=\"${CHANNEL_DISPLAY_NAME}\"" \
  --format="value(name)" 2>/dev/null | head -1 || true)"

if [ -n "$EXISTING_CHANNEL" ]; then
  echo "[INFO] 既存の通知チャンネルを再利用します: $EXISTING_CHANNEL"
  CHANNEL_ID="$EXISTING_CHANNEL"
else
  CMD=(gcloud beta monitoring channels create
    --project="$PROJECT_ID"
    --display-name="$CHANNEL_DISPLAY_NAME"
    --description="oneco-collector Cloud Run Job の実行失敗アラート通知先 (T109)"
    --type=email
    --channel-labels="email_address=${ALERT_EMAIL}"
    --format="value(name)")
  echo "[CMD] ${CMD[*]}"
  if [ "$DRY_RUN" = "true" ]; then
    CHANNEL_ID="projects/${PROJECT_ID}/notificationChannels/DRY-RUN-PLACEHOLDER"
    echo "[DRY_RUN] 実行をスキップしました (channel_id=${CHANNEL_ID} は仮値)"
  else
    CHANNEL_ID="$("${CMD[@]}")"
    echo "[INFO] 通知チャンネルを作成しました: $CHANNEL_ID"
  fi
fi

# --- 2. アラートポリシー ---
EXISTING_POLICY="$(gcloud monitoring policies list \
  --project="$PROJECT_ID" \
  --filter="displayName=\"${POLICY_DISPLAY_NAME}\"" \
  --format="value(name)" 2>/dev/null | head -1 || true)"

if [ -n "$EXISTING_POLICY" ]; then
  echo "[ERROR] 同名のポリシーが既に存在します。重複作成を避けるため中断します: $EXISTING_POLICY" >&2
  echo "        更新する場合は次を使ってください:" >&2
  echo "        gcloud monitoring policies update ${EXISTING_POLICY} --policy-from-file=${POLICY_FILE} --project=${PROJECT_ID}" >&2
  exit 1
fi

CMD=(gcloud monitoring policies create
  --project="$PROJECT_ID"
  --policy-from-file="$POLICY_FILE"
  --notification-channels="$CHANNEL_ID")
echo "[CMD] ${CMD[*]}"
if [ "$DRY_RUN" = "true" ]; then
  echo "[DRY_RUN] 実行をスキップしました"
else
  "${CMD[@]}"
  echo "[INFO] アラートポリシーを作成しました"
fi

echo "[INFO] 完了"
