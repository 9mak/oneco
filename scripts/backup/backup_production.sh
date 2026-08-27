#!/bin/bash
# Production Database Backup Script (Supabase)
#
# 背景 (2026-08-26 監査):
#   本番 DB は Supabase free プランで自動バックアップ・PITR が無い。
#   scripts/backup/backup.sh・restore.sh は旧 docker-compose 自前 PostgreSQL 前提で
#   本番には適用できない (本番は DATABASE_URL 環境変数経由の Supabase 接続文字列)。
#   誤 migration・誤 DELETE の巻き戻し手段が無かったため新設した。
#
# Usage:
#   DATABASE_URL='postgresql+asyncpg://user:pass@host:5432/db' \
#     ./scripts/backup/backup_production.sh [--retention-days N]
#
#   --retention-days N : N 日より古いバックアップファイルを削除する (デフォルト 7)
#
# 出力:
#   ${BACKUP_DIR:-./backups}/oneco_production_<timestamp>.dump.gz
#     pg_dump のカスタムフォーマット (-Fc) を gzip で追加圧縮したファイル。
#
# 前提:
#   - pg_dump / gzip が実行環境 (Cloud Run Jobs 等) にインストール済みであること
#   - DATABASE_URL は SQLAlchemy 形式 (postgresql+asyncpg://...) を許容する。
#     pg_dump は "+asyncpg" 等のドライバサフィックスを解釈できないため、
#     このスクリプト内で postgresql:// (libpq URI) に正規化してから使用する。
#
# ------------------------------------------------------------------
# RESTORE 手順 (別環境への復元 / 誤 DELETE・誤 migration からのロールバック):
#
#   1. バックアップファイルを展開する:
#        gzip -dk oneco_production_YYYYMMDD_HHMMSS.dump.gz
#
#   2. pg_restore で復元する (DATABASE_URL は復元先の接続文字列。
#      postgresql+asyncpg:// 形式のままだと pg_restore が解釈できないため
#      本スクリプトと同様に postgresql:// へ書き換えること):
#        pg_restore --clean --if-exists --no-owner --no-privileges \
#          --dbname="postgresql://user:pass@host:5432/db" \
#          oneco_production_YYYYMMDD_HHMMSS.dump
#
#      --clean --if-exists : 復元前に既存オブジェクトを DROP してから作り直す
#      --no-owner --no-privileges : Supabase 管理下のロール権限と衝突させない
#
#   3. 復元後は必ず件数・疎通を確認する:
#        psql "postgresql://user:pass@host:5432/db" -c "SELECT count(*) FROM animals;"
#        curl -f https://<本番API>/health
#
# 注意 (運用開始前に必ず確認すること):
#   - 本番 DATABASE_URL でのバックアップ実行はスクリプト作成者の環境では未検証。
#     運用開始前に一度、本番相当の接続文字列でリハーサル実行し、
#     ファイルサイズ・pg_restore --list でのテーブル一覧が妥当か確認すること。
#     (ローカルの使い捨て PostgreSQL コンテナに対しては
#      backup → drop table → pg_restore の一連の流れを検証済み。
#      pg_dump/pg_restore のメジャーバージョンが Supabase 側 PostgreSQL の
#      メジャーバージョンより新しいと、新しい GUC 由来の "SET ... = 0;" 行などで
#      無害な警告が出ることがある。実行環境の pg_dump は Supabase の
#      PostgreSQL バージョンに合わせるか、同等以上のものを使うこと)
#   - Supabase 側で追加の接続オプションが必要な場合、DATABASE_URL の
#     クエリパラメータとして含めておけば pg_dump の接続 URI としても解釈される。
#     asyncpg 固有のパラメータ名 (例: ssl=true) は libpq では無効なため、
#     その場合は sslmode=require 等 libpq 形式のパラメータ名に書き換えること。
#   - GitHub Actions workflow 化・Cloud Scheduler 連携はこのスクリプトのスコープ外。

set -euo pipefail

# --- 設定 ---
BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_DAYS=7
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# 引数解析 (backup.sh は Usage 表記が --retention-days N なのに実装は
# 位置引数 $1 を直接使う不整合があったため、本スクリプトでは実際に
# --retention-days フラグをパースする)
while [ $# -gt 0 ]; do
    case "$1" in
        --retention-days)
            RETENTION_DAYS="${2:?--retention-days には日数を指定してください}"
            shift 2
            ;;
        *)
            echo "Unknown argument: $1" >&2
            echo "Usage: $0 [--retention-days N]" >&2
            exit 1
            ;;
    esac
done

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# --- 前提チェック ---
if [ -z "${DATABASE_URL:-}" ]; then
    log_error "DATABASE_URL が未設定です。本番 Supabase の接続文字列を設定してください。"
    exit 1
fi

if ! command -v pg_dump >/dev/null 2>&1; then
    log_error "pg_dump が見つかりません。postgresql-client をインストールしてください。"
    exit 1
fi

# SQLAlchemy 形式 (postgresql+asyncpg://... 等) を pg_dump が解釈できる
# libpq URI (postgresql://...) に正規化する。
PG_DUMP_URL=$(echo "${DATABASE_URL}" | sed -E 's#^postgresql\+[a-zA-Z0-9_]+://#postgresql://#')

mkdir -p "${BACKUP_DIR}"

DUMP_FILE="${BACKUP_DIR}/oneco_production_${TIMESTAMP}.dump"
GZIP_FILE="${DUMP_FILE}.gz"

log_info "本番 DB バックアップを開始します..."
log_info "出力先: ${GZIP_FILE}"

# --- pg_dump (カスタムフォーマット: pg_restore での選択的リストア・並列リストアが可能) ---
pg_dump --format=custom --no-owner --no-privileges \
    --dbname="${PG_DUMP_URL}" \
    --file="${DUMP_FILE}"

DUMP_SIZE=$(du -h "${DUMP_FILE}" | cut -f1)
log_success "pg_dump 完了 (${DUMP_SIZE})"

# --- gzip 圧縮 ---
log_info "gzip 圧縮中..."
gzip -f "${DUMP_FILE}"
GZIP_SIZE=$(du -h "${GZIP_FILE}" | cut -f1)
log_success "圧縮完了 (${GZIP_SIZE})"

# --- 古いバックアップの削除 ---
log_info "${RETENTION_DAYS} 日より古いバックアップを削除します..."
find "${BACKUP_DIR}" -name "oneco_production_*.dump.gz" -mtime "+${RETENTION_DAYS}" -delete
REMAINING=$(find "${BACKUP_DIR}" -name "oneco_production_*.dump.gz" | wc -l | tr -d ' ')
log_success "クリーンアップ完了 (残り ${REMAINING} 件)"

# --- 整合性検証 ---
log_info "バックアップの整合性を検証します..."
if gzip -t "${GZIP_FILE}"; then
    log_success "整合性チェック OK"
else
    log_error "整合性チェックに失敗しました"
    exit 1
fi

# Summary
echo ""
echo "=========================================="
log_success "本番 DB バックアップが完了しました"
echo "  出力先: ${GZIP_FILE}"
echo "  サイズ: ${GZIP_SIZE}"
echo ""
echo "リストア手順はこのファイル冒頭のコメントを参照してください。"
echo "=========================================="
