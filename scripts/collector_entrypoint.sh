#!/usr/bin/env bash
# Cloud Run Jobs 上で夜間収集を実行するエントリポイント。
#
# data-collector.yml (GitHub Actions 版) と同じ手順を再現する:
#   1. リポジトリを shallow clone し CWD にする
#      (状態ファイル data/*.yaml, output/, snapshots/ が相対パスのまま動く)
#   2. alembic upgrade head (冪等。collector はデプロイ経路を介さず本番 DB を
#      直接触るため、ここで打たないと新カラム欠如で INSERT が全滅する)
#   3. python -m data_collector
#   4. 状態ファイルを commit & push (競合時は pull --rebase で最大3回リトライ)
#
# 必要な環境変数:
#   GIT_DEPLOY_KEY   : 9mak/oneco の書き込み可 deploy key (秘密鍵, Secret Manager)
#   DATABASE_URL     : 本番 DB。未設定なら DB 書き込みと alembic をスキップ (検証モード)
#   COLLECTOR_SKIP_PUSH=1 : 状態ファイルの push を抑止 (検証モード)
set -euo pipefail

REPO_SSH_URL="${COLLECTOR_REPO_SSH_URL:-git@github.com:9mak/oneco.git}"
WORK_DIR="${COLLECTOR_WORK_DIR:-/tmp/oneco-work}"

# --- deploy key と GitHub ホスト鍵の設定 ---
# ホスト鍵は https://api.github.com/meta の公開値 (2026-08-14 取得) を固定で信頼する。
# ssh-keyscan での TOFU は中間者を検出できないため使わない。
mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"
printf '%s\n' "$GIT_DEPLOY_KEY" > "$HOME/.ssh/id_ed25519"
chmod 600 "$HOME/.ssh/id_ed25519"
cat > "$HOME/.ssh/known_hosts" <<'KNOWN_HOSTS'
github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl
github.com ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBEmKSENjQEezOmxkZMy7opKgwFB9nkt5YRrYMjNuG5N87uRgg6CLrbo5wAdT/y6v0mKV0U2w0WZ2YB/++Tpockg=
github.com ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCj7ndNxQowgcQnjshcLrqPEiiphnt+VTTvDP6mHBL9j1aNUkY4Ue1gvwnGLVlOhGeYrnZaMgRK6+PKCUXaDbC7qtbW8gIkhL7aGCsOr/C56SJMy/BCZfxd1nWzAOxSDPgVsmerOBYfNqltV9/hWCqBywINIR+5dIg6JTJ72pcEpEjcYgXkE2YEFXV1JHnsKgbLWNlhScqb2UmyRkQyytRLtL+38TGxkxCflmO+5Z8CSSNY7GidjMIZ7Q4zMjA2n1nGrlTDkzwDCsw+wqFPGQA179cnfGWOWRVruj16z6XyvxvjJwbz0wQZ75XK5tKSb7FNyeIEs4TT4jk+S4dhPeAUC5y+bDYirYgM4GC7uEnztnZyaVWQ7B381AK4Qdrwt51ZqExKbQpTUNn+EjqoTwvqNj4kqx5QUCI0ThS/YkOxJCXmPUWZbhjpCg56i+2aB6CmK2JGhn57K5mj0MNdBXA4/WnwH6XoPWJzK5Nyu2zB3nAZp+S5hpQs+p1vN1/wsjk=
KNOWN_HOSTS
export GIT_SSH_COMMAND="ssh -i $HOME/.ssh/id_ed25519 -o UserKnownHostsFile=$HOME/.ssh/known_hosts -o StrictHostKeyChecking=yes"

# --- clone して作業ディレクトリへ ---
rm -rf "$WORK_DIR"
git clone --depth 1 "$REPO_SSH_URL" "$WORK_DIR"
cd "$WORK_DIR"

# --- DB スキーマを最新化 (冪等) ---
if [ -n "${DATABASE_URL:-}" ]; then
  alembic upgrade head
else
  echo "DATABASE_URL 未設定: alembic と DB 書き込みをスキップ (検証モード)"
fi

# --- 収集本体 ---
# 失敗 (全サイト失敗・失敗率ゲート超過) なら set -e でここで終了し、
# 状態ファイルは push されない (Actions 版の if: success() と同じ挙動)。
# 収集内エラーの Slack/Discord 通知は collector 自身が送る。
python -m data_collector

# --- 状態ファイルの commit & push ---
if [ "${COLLECTOR_SKIP_PUSH:-0}" = "1" ]; then
  echo "COLLECTOR_SKIP_PUSH=1: 状態ファイルの push をスキップ (検証モード)"
  exit 0
fi

git config user.name "oneco-collector-job"
git config user.email "oneco-collector-job@users.noreply.github.com"

for f in output/animals.json snapshots/latest.json \
         data/broken_sites.yaml data/site_baselines.yaml \
         data/field_quality_drift.yaml; do
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
