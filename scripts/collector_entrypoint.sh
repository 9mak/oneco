#!/usr/bin/env bash
# Cloud Run Jobs 上で夜間収集を実行するエントリポイント。
#
# 手順:
#   1. 9mak/oneco (public) を認証なし HTTPS で shallow clone し APP_DIR とする。
#      alembic.ini/alembic/、および一部モジュール (alembic/env.py 含む) が
#      `from src.data_collector...` という CWD 相対 import に依存しているため、
#      src/ ディレクトリ構造がそのまま CWD にある必要がある。public repo なので
#      読み取りに鍵は不要 (このリポジトリへの書き込みは一切行わない)。
#   2. alembic upgrade head (APP_DIR 内で実行。冪等)
#   3. 9mak/oneco-state (private, 状態ファイル専用) を deploy key 付き SSH で
#      shallow clone し STATE_DIR とする
#   4. STATE_DIR の状態ファイルを APP_DIR の対応パスへコピーし、前回の収集状態を復元する
#      (SnapshotStore/OutputWriter は env var オーバーライドを持たず CWD 相対パス
#      固定のため、CWD=APP_DIR に物理コピーする必要がある)
#   5. python -m data_collector (CWD=APP_DIR)
#   6. APP_DIR で更新された状態ファイルを STATE_DIR へコピーし戻し、
#      STATE_DIR 側で commit & push (競合時は pull --rebase で最大3回リトライ)
#
# T112 (2026-08-31): 以前は 9mak/oneco 本体に対する読み書き両用 deploy key
# (GIT_DEPLOY_KEY) 1本で clone・alembic・状態ファイル push の全てを賄っていた。
# しかしこの鍵はリポジトリ全体への書き込み権限 (read_only:false) を持つため、
# 鍵漏洩時に「通常pushによるソースコード/workflow改ざん」という経路が
# 未対処のまま残っていた。状態ファイル5点を専用の private リポジトリ
# 9mak/oneco-state に分離し、新しい deploy key (GIT_STATE_DEPLOY_KEY) の
# 書き込み権限をその5ファイルだけに縮小した。9mak/oneco は public repo なので
# ソース取得は認証不要の HTTPS clone で行い、そちらへの書き込みは行わない。
#
# 必要な環境変数:
#   GIT_STATE_DEPLOY_KEY  : 9mak/oneco-state の書き込み可 deploy key (秘密鍵, Secret Manager)
#                           (旧 GIT_DEPLOY_KEY を置き換え。9mak/oneco 本体への書き込み権限は持たない)
#   DATABASE_URL          : 本番 DB。未設定なら DB 書き込みと alembic をスキップ (検証モード)
#   COLLECTOR_SKIP_PUSH=1 : 状態ファイルの push を抑止 (検証モード)
set -euo pipefail

APP_REPO_HTTPS_URL="${COLLECTOR_APP_REPO_HTTPS_URL:-https://github.com/9mak/oneco.git}"
STATE_REPO_SSH_URL="${COLLECTOR_STATE_REPO_SSH_URL:-git@github.com:9mak/oneco-state.git}"
APP_DIR="${COLLECTOR_APP_DIR:-/tmp/oneco-app}"
STATE_DIR="${COLLECTOR_STATE_DIR:-/tmp/oneco-state}"

# 状態ファイルの一覧 (9mak/oneco-state <-> APP_DIR の間でコピーする対象)。
STATE_FILES=(
  "data/broken_sites.yaml"
  "data/site_baselines.yaml"
  "data/field_quality_drift.yaml"
  "output/animals.json"
  "snapshots/latest.json"
)

# --- アプリ本体を認証なし HTTPS で取得 (public repo・読み取り専用・鍵不要) ---
rm -rf "$APP_DIR"
git clone --depth 1 "$APP_REPO_HTTPS_URL" "$APP_DIR"
cd "$APP_DIR"

# --- DB スキーマを最新化 (冪等) ---
if [ -n "${DATABASE_URL:-}" ]; then
  alembic upgrade head
else
  echo "DATABASE_URL 未設定: alembic と DB 書き込みをスキップ (検証モード)"
fi

# --- deploy key と GitHub ホスト鍵の設定 (oneco-state への読み書き用) ---
# ホスト鍵は https://api.github.com/meta の公開値 (2026-08-14 取得) を固定で信頼する。
# ssh-keyscan での TOFU は中間者を検出できないため使わない。
mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"
printf '%s\n' "$GIT_STATE_DEPLOY_KEY" > "$HOME/.ssh/id_ed25519"
chmod 600 "$HOME/.ssh/id_ed25519"
cat > "$HOME/.ssh/known_hosts" <<'KNOWN_HOSTS'
github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl
github.com ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBEmKSENjQEezOmxkZMy7opKgwFB9nkt5YRrYMjNuG5N87uRgg6CLrbo5wAdT/y6v0mKV0U2w0WZ2YB/++Tpockg=
github.com ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCj7ndNxQowgcQnjshcLrqPEiiphnt+VTTvDP6mHBL9j1aNUkY4Ue1gvwnGLVlOhGeYrnZaMgRK6+PKCUXaDbC7qtbW8gIkhL7aGCsOr/C56SJMy/BCZfxd1nWzAOxSDPgVsmerOBYfNqltV9/hWCqBywINIR+5dIg6JTJ72pcEpEjcYgXkE2YEFXV1JHnsKgbLWNlhScqb2UmyRkQyytRLtL+38TGxkxCflmO+5Z8CSSNY7GidjMIZ7Q4zMjA2n1nGrlTDkzwDCsw+wqFPGQA179cnfGWOWRVruj16z6XyvxvjJwbz0wQZ75XK5tKSb7FNyeIEs4TT4jk+S4dhPeAUC5y+bDYirYgM4GC7uEnztnZyaVWQ7B381AK4Qdrwt51ZqExKbQpTUNn+EjqoTwvqNj4kqx5QUCI0ThS/YkOxJCXmPUWZbhjpCg56i+2aB6CmK2JGhn57K5mj0MNdBXA4/WnwH6XoPWJzK5Nyu2zB3nAZp+S5hpQs+p1vN1/wsjk=
KNOWN_HOSTS
export GIT_SSH_COMMAND="ssh -i $HOME/.ssh/id_ed25519 -o UserKnownHostsFile=$HOME/.ssh/known_hosts -o StrictHostKeyChecking=yes"

# --- 状態ファイル専用リポジトリを clone し、前回状態を APP_DIR に復元 ---
rm -rf "$STATE_DIR"
git clone --depth 1 "$STATE_REPO_SSH_URL" "$STATE_DIR"
mkdir -p "$APP_DIR/data" "$APP_DIR/output" "$APP_DIR/snapshots"
for f in "${STATE_FILES[@]}"; do
  [ -e "$STATE_DIR/$f" ] && cp "$STATE_DIR/$f" "$APP_DIR/$f" || true
done

# --- 収集本体 (CWD=APP_DIR) ---
# 失敗 (全サイト失敗・失敗率ゲート超過) なら set -e でここで終了し、
# 状態ファイルは push されない (Actions 版の if: success() と同じ挙動)。
# 収集内エラーの Slack/Discord 通知は collector 自身が送る。
python -m data_collector

# --- 状態ファイルを oneco-state へ書き戻し、commit & push ---
if [ "${COLLECTOR_SKIP_PUSH:-0}" = "1" ]; then
  echo "COLLECTOR_SKIP_PUSH=1: 状態ファイルの push をスキップ (検証モード)"
  exit 0
fi

for f in "${STATE_FILES[@]}"; do
  [ -e "$APP_DIR/$f" ] && cp "$APP_DIR/$f" "$STATE_DIR/$f" || true
done

cd "$STATE_DIR"
git config user.name "oneco-collector-job"
git config user.email "oneco-collector-job@users.noreply.github.com"

for f in "${STATE_FILES[@]}"; do
  [ -e "$f" ] && git add "$f" || true
done

if git diff --staged --quiet; then
  echo "No changes to commit"
  exit 0
fi

git commit -m "Update collection data [automated]

🤖 Generated with Claude Code (https://claude.com/claude-code)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"

# push retry: sns-publish 等の他ジョブと衝突したら rebase してやり直す (最大3回)。
# 失敗しても exit 0 (best-effort)。次回 run が全量を再収集・再記録する。
for attempt in 1 2 3; do
  if git push origin HEAD:main; then
    echo "Push successful on attempt $attempt"
    exit 0
  fi
  echo "Push attempt $attempt failed (likely upstream changed)"
  if ! git pull --rebase origin main; then
    echo "git pull --rebase failed; aborting retry"
    exit 0
  fi
  sleep $((attempt * 3))
done
echo "Push failed after 3 attempts; state will be retried in the next run"
exit 0
