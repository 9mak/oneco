#!/usr/bin/env bash
# oneco v2 日次収集（収集サーバー = VPS 用）。systemd の oneco-collect.timer から毎日 JST 0:00 に呼ばれる。
#
#   run（全ページ収集）→ notify（異常があれば Discord）→ build（静的サイト）→ Cloudflare Pages へ deploy
#   → 全部成功したら HEALTHCHECK_URL へ ping。
#
# どこかで失敗しても途中で止めず最後まで進み、最後に 0（全部成功）か 1（どれかが失敗）を返す。
# 収集が失敗しても build/deploy は「前回の data/latest.json」で走るので、サイトは昨日のまま出続ける。
#
# 環境変数（/etc/oneco/collect.env に置き、systemd の EnvironmentFile で読む）:
#   ONECO_V2_DIR            v2 ディレクトリ（既定: このスクリプトの 1 つ上）
#   ONECO_PY                venv の python（既定: $ONECO_V2_DIR/../.venv/bin/python）
#   ONECO_LOG_DIR           ログ置き場（既定: $ONECO_V2_DIR/logs）
#   DISCORD_WEBHOOK_URL     notify の送り先（無ければ表示だけ）
#   ANTHROPIC_API_KEY       AI 修復（無ければ修復しない）
#   ONECO_AI_REPAIR         1 で AI 修復を有効化
#   CLOUDFLARE_API_TOKEN / CLOUDFLARE_ACCOUNT_ID / ONECO_PAGES_PROJECT   Pages deploy（3 つ揃わなければ deploy を飛ばす）
#   HEALTHCHECK_URL         healthchecks.io などの ping URL（無ければ飛ばす）
#   WRANGLER                wrangler の呼び方（既定: "npx --yes wrangler"）
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
V2_DIR="${ONECO_V2_DIR:-$(dirname "$SCRIPT_DIR")}"
PY="${ONECO_PY:-$V2_DIR/../.venv/bin/python}"
LOG_DIR="${ONECO_LOG_DIR:-$V2_DIR/logs}"
WRANGLER="${WRANGLER:-npx --yes wrangler}"
DATE="$(TZ=Asia/Tokyo date +%Y-%m-%d)"
LOG="$LOG_DIR/collect-$DATE.log"

mkdir -p "$LOG_DIR"
# 以降の標準出力・標準エラーはログにも残す（journalctl でも見える）
exec > >(tee -a "$LOG") 2>&1

export PYTHONPATH="$V2_DIR"   # `python -m collector` を cd 無しで動かす
export PYTHONUNBUFFERED=1

rc=0
failed_steps=""

# step <名前> <コマンド...>: 失敗しても止めない。失敗を記録するだけ
step() {
  local name="$1"
  shift
  echo "== [$(date '+%H:%M:%S')] $name"
  if "$@"; then
    echo "-- $name: ok"
  else
    local code=$?
    echo "-- $name: 失敗 (exit $code)"
    rc=1
    failed_steps="$failed_steps $name"
  fi
}

echo "#### oneco v2 collect $DATE (v2=$V2_DIR python=$PY)"

if [ ! -x "$PY" ]; then
  echo "python が無い: $PY"
  rc=1
fi

# 1. 収集（--date を渡さなければ collector 側が JST の今日を使う）
step run "$PY" -m collector run

# 2. 通知（直近の report を見て、異常があるときだけ Discord に 1 通）
step notify "$PY" -m collector notify

# 3. 静的サイト生成（data/latest.json → site/dist）
#    `python -m site.build` は標準ライブラリの site モジュールに阻まれて動かないので、ファイルを直接実行する
step build "$PY" "$V2_DIR/site/build.py" --data "$V2_DIR/data/latest.json" --out "$V2_DIR/site/dist"

# 4. Cloudflare Pages へ deploy
#    認証は CLOUDFLARE_API_TOKEN（VPS 向け）か、`wrangler login` で保存した OAuth（手元の Mac 向け）のどちらか。
#    どちらも無ければ wrangler が失敗して deploy が「失敗」に数えられ、通知に載る
if [ -n "${ONECO_PAGES_PROJECT:-}" ]; then
  if [ -d "$V2_DIR/site/dist" ]; then
    # Pages の新規プロジェクトは Workers（static assets）に統合されたので `wrangler deploy` を使う（設定は ops/wrangler.jsonc）。
    # ONECO_PAGES_PROJECT は Worker 名（wrangler.jsonc の name を上書き）
    # shellcheck disable=SC2086  # WRANGLER は "npx --yes wrangler" のように単語分割させたい
    step deploy $WRANGLER deploy --config "$V2_DIR/ops/wrangler.jsonc" --name "$ONECO_PAGES_PROJECT"
  else
    echo "== deploy: site/dist が無いので飛ばす"
    rc=1
    failed_steps="$failed_steps deploy"
  fi
else
  echo "== deploy: ONECO_PAGES_PROJECT が無いので飛ばす"
fi

# 5. 死活監視への ping（全部成功したときだけ本体 URL。失敗時は /fail を叩いて「失敗した」と知らせる）
if [ -n "${HEALTHCHECK_URL:-}" ]; then
  if [ "$rc" -eq 0 ]; then
    step healthcheck curl -fsS -m 10 --retry 3 -o /dev/null "$HEALTHCHECK_URL"
  else
    echo "== healthcheck: 失敗があるので ${HEALTHCHECK_URL}/fail へ"
    curl -fsS -m 10 --retry 3 -o /dev/null "${HEALTHCHECK_URL}/fail" || echo "-- healthcheck(/fail): 送れなかった"
  fi
else
  echo "== healthcheck: HEALTHCHECK_URL が無いので飛ばす"
fi

if [ "$rc" -eq 0 ]; then
  echo "#### 完了: 全部成功"
else
  echo "#### 完了: 失敗あり ->$failed_steps"
  # notify 工程は report（ページ単位の異常）しか見ないので、run の落ち・build・deploy の失敗はここで Discord に送る
  if [ -n "${DISCORD_WEBHOOK_URL:-}" ]; then
    msg="oneco v2 $DATE: 失敗した工程 ->$failed_steps（ログ: $LOG）"
    payload="$("$PY" -c 'import json,sys; print(json.dumps({"content": sys.argv[1]}))' "$msg" 2>/dev/null \
      || printf '{"content": "oneco v2 %s: 失敗した工程 ->%s"}' "$DATE" "$failed_steps")"
    curl -fsS -m 15 --retry 2 -H 'Content-Type: application/json' -o /dev/null --data "$payload" "$DISCORD_WEBHOOK_URL" \
      || echo "-- Discord に送れなかった"
  fi
fi
exit "$rc"
