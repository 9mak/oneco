#!/usr/bin/env bash
# 公開データを指定日の animals-<日付>.json に戻して公開する（W006 T623 の rollback 手順。promote → build → deploy → 公開確認）。
#   bash v2/ops/rollback.sh 2026-10-14            # その日に戻す
#   bash v2/ops/rollback.sh 2026-10-15            # 今日の分に戻し戻す
# 使う場面: 据え置かれた日を確認のうえ公開する（OPERATIONS.md 3-1）、レシピやコードの変更で壊れたデータを公開してしまった日に前日へ戻す。
# 本番の Mac で動かす前提（collect.env と wrangler の OAuth があること）。VPS なら ONECO_V2_DIR・ONECO_PY・collect.env の場所を環境変数で渡す。
# 2026-10-15 の試験: 10/14 へ戻して 10 秒後に公開 data.json の date が 10/14（etag が変わり cf-cache-status MISS→HIT）、10/15 へ戻し戻しも同様。
set -u
DATE="${1:?使い方: rollback.sh YYYY-MM-DD}"
case "$DATE" in [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]) ;; *) echo "日付の形が違う: $DATE" >&2; exit 2 ;; esac
V2="${ONECO_V2_DIR:-$HOME/oneco-collect/v2}"
PY="${ONECO_PY:-$V2/../.venv/bin/python}"
ENV_FILE="${ONECO_ENV_FILE:-$HOME/.config/oneco/collect.env}"
WRANGLER="${WRANGLER:-npx --yes wrangler}"
set -a
# shellcheck disable=SC1090
[ -f "$ENV_FILE" ] && . "$ENV_FILE"
set +a
export PYTHONPATH="$V2"
: "${ONECO_PAGES_PROJECT:?ONECO_PAGES_PROJECT が無い（collect.env）}"

echo "#### rollback → $DATE  $(date '+%F %T')"
"$PY" -m collector promote --date "$DATE" || exit 1
"$PY" "$V2/site/build.py" --data "$V2/data/latest.json" --out "$V2/site/dist" || exit 1
# shellcheck disable=SC2086
$WRANGLER deploy --config "$V2/ops/wrangler.jsonc" --name "$ONECO_PAGES_PROJECT" || exit 1

BASE="${ONECO_SITE_URL:-$(sed -n 's/.*"base_url": *"\([^"]*\)".*/\1/p' "$V2/site/config.json")}"
if [ -n "$BASE" ]; then
  sleep 10
  live="$(curl -sS -m 30 "$BASE/data.json?rollback=$(date +%s)" | head -c 120 | tr -d '\n ')"
  echo "公開 data.json: $live"
  case "$live" in *"\"date\":\"$DATE\""*) echo "-- 公開側が $DATE になった" ;; *) echo "-- まだ $DATE になっていない（数十秒おいて $BASE/data.json を見る）"; exit 1 ;; esac
fi
