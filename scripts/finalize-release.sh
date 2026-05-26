#!/usr/bin/env bash
# Phase 1.5 リリース最終確定スクリプト
#
# Claude が autonomous に実行できない 3 つのステップを 1 コマンドで実行する:
#   1. 5 PR (#41 #44 #42 #43 #45) を順次 squash merge
#   2. workflow_dispatch で data-collector を即時起動 (翌日 0:00 を待たない)
#   3. workflow 完了監視 + broken_sites.yaml 結果確認
#
# 使い方:
#   bash scripts/finalize-release.sh
#
# 前提:
#   - macOS Keychain に `oneco-github-token` が登録されていること
#   - gh CLI がインストール済み

set -euo pipefail

export GITHUB_TOKEN="$(security find-generic-password -a "$USER" -s "oneco-github-token" -w)"

echo "═══════════════════════════════════════════════════════════════"
echo "  Phase 1.5 リリース最終確定"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# ───────── Step 1: PR マージ ─────────
echo "▶ Step 1: 5 PR を順次 squash merge"
echo ""

# 順序: データ (#41) → adapter 修正 (#44) → UI 追加 (#42) → 通知 (#43) → docs (#45)
for pr in 41 44 42 43 45; do
  echo "  ─ Merging PR #${pr}..."
  if gh pr merge "${pr}" --squash --delete-branch 2>&1; then
    echo "  ✓ PR #${pr} merged"
  else
    echo "  ✗ PR #${pr} merge failed (skipping subsequent merges)"
    exit 1
  fi
  echo ""
done

echo "✓ Step 1 完了: 全 5 PR マージ済み"
echo ""

# ───────── Step 2: workflow_dispatch ─────────
echo "▶ Step 2: data-collector workflow を即時起動"
echo ""

gh workflow run data-collector.yml
echo "  ✓ workflow_dispatch 送信完了"
echo ""
echo "  ※ run 開始まで数秒、完了まで 40-50 分かかります"
echo ""

# 最新 run の URL を表示
sleep 5
LATEST_RUN_URL=$(gh run list --workflow=data-collector.yml --limit 1 --json url --jq '.[0].url')
echo "  ▷ 最新 run URL: ${LATEST_RUN_URL}"
echo ""

# ───────── Step 3: 結果確認の案内 ─────────
echo "▶ Step 3: 完了後の確認手順"
echo ""
echo "  workflow 完了後、次の commit が自動で main に push される:"
echo "    'Update collection data [automated]'"
echo ""
echo "  最終確認コマンド:"
echo "    git pull origin main"
echo "    cat data/broken_sites.yaml"
echo ""
echo "  期待される結果:"
echo "    - broken_sites.yaml が {} (空) もしくは consec:0 のエントリのみ"
echo "    - consec:3 で auto-skip されているサイトが 0 件"
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  リリース確定はこの workflow 結果次第。"
echo "  結果確認したら Claude に戻って報告してください。"
echo "═══════════════════════════════════════════════════════════════"
