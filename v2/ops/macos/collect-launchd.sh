#!/usr/bin/env bash
# launchd から呼ばれる入口（Mac 版）。env を読む → 本番クローンを main に追従（git pull --ff-only）→ ops/collect.sh。
# collect.sh を起動すらできなかった日（権限・パス違い）は Discord に 1 通送る。collect.sh の中の失敗は collect.sh 自身が送る。
# 本番クローンは ~/Desktop ・ ~/Documents ・ ~/Downloads の外（既定 ~/oneco-collect）に置く。launchd から起動した bash には
# それらの保護フォルダを読む権限（TCC）が無く、`Operation not permitted` で止まる（2026-10-01〜02 に 2 日分飛んだ）。
# 全体を関数にしてから最後に呼ぶ: git pull でこのファイル自身が書き換わっても、実行中の bash は読み終えた定義で動く。
set -u

discord() {  # $1 = 本文。DISCORD_WEBHOOK_URL が無ければ表示だけ
  [ -n "${DISCORD_WEBHOOK_URL:-}" ] || { echo "$1"; return 0; }
  local payload
  payload="$(printf '%s' "$1" | "${ONECO_PY:-python3}" -c 'import json,sys; print(json.dumps({"content": sys.stdin.read()}))')"
  curl -fsS -m 15 --retry 2 -H 'Content-Type: application/json' -o /dev/null --data "$payload" "$DISCORD_WEBHOOK_URL" \
    || echo "Discord に送れなかった: $1"
}

main() {
  set -a
  # shellcheck disable=SC1091
  [ -f "$HOME/.config/oneco/collect.env" ] && . "$HOME/.config/oneco/collect.env"
  set +a
  local v2="${ONECO_V2_DIR:?ONECO_V2_DIR が無い（plist の EnvironmentVariables か collect.env に書く）}"
  local repo
  repo="$(dirname "$v2")"
  echo "#### [$(date '+%F %T')] launchd 起動 (repo=$repo)"
  if [ "${ONECO_GIT_PULL:-1}" = "1" ] && [ -d "$repo/.git" ]; then
    local pull_out
    if pull_out="$(git -C "$repo" pull --ff-only -q origin main 2>&1)"; then
      echo "git pull: main @ $(git -C "$repo" rev-parse --short HEAD)"
    else
      # 2026-10-20〜23: 本番クローンの手元の変更で pull が止まり続け、ログにしか出ず 3 日気づかなかった。Discord にも送る
      [ -n "$pull_out" ] && echo "$pull_out"
      local head
      head="$(git -C "$repo" rev-parse --short HEAD)"
      echo "git pull に失敗（ネットワークか競合）。前回のコード @ $head で続行"
      discord "oneco v2: 本番クローンの git pull に失敗。前回のコード @ $head のまま収集する（main の修正が入らない）。$(printf '%s' "$pull_out" | head -n 1) / 手元の変更なら git -C $repo status で確認"
    fi
  fi
  "$v2/ops/collect.sh"
  local rc=$?
  if [ "$rc" -ge 126 ]; then   # 126/127 = 起動できない（権限・パス違い）。collect.sh 自身の失敗（1）は中で通知済み
    echo "collect.sh を起動できなかった (exit $rc): $v2/ops/collect.sh"
    discord "oneco v2: 収集を起動できなかった (exit $rc)。launchd の bash が $v2/ops/collect.sh を実行できない（保護フォルダの下にある、か、パス違い）。ops/macos/install.sh を入れ直す"
  fi
  return "$rc"
}

main "$@"
