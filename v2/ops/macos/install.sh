#!/usr/bin/env bash
# oneco v2 日次収集を Mac の launchd に登録する（ターミナルから実行。Claude Code のサンドボックスからは launchctl が拒否される）。
#
#   bash v2/ops/macos/install.sh            # 登録（既にあれば入れ替え）
#   bash v2/ops/macos/install.sh --remove   # 解除
#
# やること: ~/.config/oneco/collect.env が無ければ example を置く → plist の __V2_DIR__ / __PY__ をこの Mac の
#           パスに置き換えて ~/Library/LaunchAgents へ置く → launchctl で読み込む → 次回の実行予定を表示する。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
V2_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
PY="${ONECO_PY:-$V2_DIR/../.venv/bin/python}"
PY="$(cd "$(dirname "$PY")" && pwd)/$(basename "$PY")"
LABEL="com.oneco.collect"
PLIST_DST="$HOME/Library/LaunchAgents/$LABEL.plist"
ENV_DIR="$HOME/.config/oneco"
ENV_FILE="$ENV_DIR/collect.env"
DOMAIN="gui/$(id -u)"

if [ "${1:-}" = "--remove" ]; then
  launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
  rm -f "$PLIST_DST"
  echo "解除した: $PLIST_DST（$ENV_FILE は残している）"
  exit 0
fi

[ -x "$PY" ] || { echo "python が無い: $PY（.venv を作ってから）"; exit 1; }
command -v npx >/dev/null || { echo "npx が無い（wrangler に Node.js が要る。brew install node）"; exit 1; }

mkdir -p "$ENV_DIR" "$V2_DIR/logs" "$HOME/Library/LaunchAgents"
if [ ! -f "$ENV_FILE" ]; then
  cp "$SCRIPT_DIR/collect.env.example" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  echo "環境変数ファイルを置いた: $ENV_FILE（Cloudflare の値を埋めるまで deploy は飛ばされる）"
fi

sed -e "s|__V2_DIR__|$V2_DIR|g" -e "s|__PY__|$PY|g" "$SCRIPT_DIR/$LABEL.plist" > "$PLIST_DST"
plutil -lint "$PLIST_DST" >/dev/null

launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
launchctl bootstrap "$DOMAIN" "$PLIST_DST"
launchctl enable "$DOMAIN/$LABEL"

echo "登録した: $PLIST_DST"
launchctl print "$DOMAIN/$LABEL" | grep -E "state|last exit|run interval|program" | head -5 || true
echo
echo "毎日 0:05 JST に動く。今すぐ試すなら:  launchctl kickstart -k $DOMAIN/$LABEL  → tail -f $V2_DIR/logs/launchd.log"
