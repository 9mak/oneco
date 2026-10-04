#!/usr/bin/env bash
# oneco v2 日次収集を Mac の launchd に登録する。
#
#   bash v2/ops/macos/install.sh            # 登録（既にあれば入れ替え）
#   bash v2/ops/macos/install.sh --remove   # 解除（本番クローンと collect.env は残す）
#   ONECO_RUN_DIR=~/somewhere bash v2/ops/macos/install.sh   # 本番クローンの場所を変える（既定 ~/oneco-collect）
#
# やること:
#   1. 本番クローン（既定 ~/oneco-collect）を作る（無ければ `git clone --branch main`、あれば `git pull --ff-only`）。
#      開発用の checkout（この Mac では ~/Desktop/oneco）から直接は動かさない。launchd から起動した bash は
#      ~/Desktop ・ ~/Documents ・ ~/Downloads（macOS の保護フォルダ、TCC）を読めず `Operation not permitted` で止まるため。
#      毎日の実行時に collect-launchd.sh が main を pull するので、main に merge すれば翌日の収集から反映される。
#   2. 本番クローンに .venv を作り、v2/requirements.txt と Playwright の Chromium を入れる（入っていれば何もしない）
#   3. ~/.config/oneco/collect.env が無ければ example を置く
#   4. plist の __REPO_DIR__ / __V2_DIR__ / __PY__ を埋めて ~/Library/LaunchAgents へ置き、launchctl で読み込む
set -euo pipefail
# 変数の直後に全角文字を続けるときは必ず ${VAR} と書く。$VAR（ だと bash（ロケールによる）が全角の先頭バイトを
# 変数名の一部と読み、set -u で「unbound variable」になって止まる（2026-10-04 に 81 行目で発生）

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_REPO="$(cd "$SCRIPT_DIR/../../.." && pwd)"      # このスクリプトがある checkout（clone 元の URL を取るだけ）
RUN_DIR="${ONECO_RUN_DIR:-$HOME/oneco-collect}"
LABEL="com.oneco.collect"
PLIST_DST="$HOME/Library/LaunchAgents/$LABEL.plist"
ENV_DIR="$HOME/.config/oneco"
ENV_FILE="$ENV_DIR/collect.env"
DOMAIN="gui/$(id -u)"

if [ "${1:-}" = "--remove" ]; then
  launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
  rm -f "$PLIST_DST"
  echo "解除した: ${PLIST_DST}（${RUN_DIR} と ${ENV_FILE} は残している）"
  exit 0
fi

case "$RUN_DIR" in
  "$HOME/Desktop"/*|"$HOME/Documents"/*|"$HOME/Downloads"/*)
    echo "ONECO_RUN_DIR=$RUN_DIR は macOS の保護フォルダの下。launchd の bash が読めないので ~/Desktop ・ ~/Documents ・ ~/Downloads の外にする" >&2
    exit 1 ;;
esac
command -v git >/dev/null || { echo "git が無い（xcode-select --install）" >&2; exit 1; }
command -v npx >/dev/null || { echo "npx が無い（wrangler に Node.js が要る。brew install node）" >&2; exit 1; }
PY_SYS="$(command -v python3.11 || command -v python3 || true)"
[ -n "$PY_SYS" ] || { echo "python3 が無い（brew install python@3.11）" >&2; exit 1; }

# 1. 本番クローン
ORIGIN="$(git -C "$SRC_REPO" remote get-url origin 2>/dev/null || echo https://github.com/9mak/oneco.git)"
if [ -d "$RUN_DIR/.git" ]; then
  echo "本番クローンを更新: $RUN_DIR"
  git -C "$RUN_DIR" pull --ff-only -q origin main
else
  echo "本番クローンを作る: $RUN_DIR ← $ORIGIN (main)"
  git clone -q --branch main "$ORIGIN" "$RUN_DIR"
fi
V2_DIR="$RUN_DIR/v2"
PY="$RUN_DIR/.venv/bin/python"

# 2. venv・依存・Chromium
if [ ! -x "$PY" ]; then
  echo "venv を作る: $RUN_DIR/.venv ($PY_SYS)"
  "$PY_SYS" -m venv "$RUN_DIR/.venv"
fi
"$PY" -m pip install -q --upgrade pip
"$PY" -m pip install -q -r "$V2_DIR/requirements.txt"
"$RUN_DIR/.venv/bin/playwright" install chromium >/dev/null   # 入っていれば一瞬で終わる（~/Library/Caches/ms-playwright に共有）

# 3. 環境変数ファイル
mkdir -p "$ENV_DIR" "$V2_DIR/logs" "$HOME/Library/LaunchAgents"
if [ ! -f "$ENV_FILE" ]; then
  cp "$SCRIPT_DIR/collect.env.example" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  echo "環境変数ファイルを置いた: ${ENV_FILE}（ONECO_PAGES_PROJECT 等を埋めるまで deploy は飛ばされる）"
fi

# 4. plist
sed -e "s|__REPO_DIR__|$RUN_DIR|g" -e "s|__V2_DIR__|$V2_DIR|g" -e "s|__PY__|$PY|g" "$SCRIPT_DIR/$LABEL.plist" > "$PLIST_DST"
plutil -lint "$PLIST_DST" >/dev/null

launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
launchctl bootstrap "$DOMAIN" "$PLIST_DST"
launchctl enable "$DOMAIN/$LABEL"

echo "登録した: ${PLIST_DST}（repo=${RUN_DIR} python=${PY}）"
launchctl print "$DOMAIN/$LABEL" | grep -E "state|last exit|program" | head -4 || true
echo
echo "毎日 0:05 JST に動く。今すぐ試すなら:  launchctl kickstart -k $DOMAIN/$LABEL  → tail -f $V2_DIR/logs/launchd.log"
