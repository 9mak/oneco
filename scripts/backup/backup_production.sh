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
#   DATABASE_URL_DIRECT='postgresql+asyncpg://user:pass@db.<project>.supabase.co:5432/db' \
#   BACKUP_GCS_BUCKET='oneco-production-backups' \
#     ./scripts/backup/backup_production.sh [--retention-days N]
#
#   --retention-days N : N 日より古い「ローカル」バックアップファイルを削除する (デフォルト 7)
#                        (GCS 側のライフサイクル/保持期間はバケット側の設定に委ねる。
#                         このスクリプトは削除しない)
#
# 環境変数:
#   DATABASE_URL_DIRECT : (推奨) Supabase の Direct Connection 接続文字列。
#                          pg_dump/pg_restore 等のバックアップ・管理ツールは
#                          Direct Connection (ポート 5432, db.<project>.supabase.co) を
#                          使うことを Supabase 公式が明記している
#                          (https://supabase.com/docs/guides/database/connecting-to-postgres
#                           "Use for migrations, pg_dump, backup and management tools")。
#                          未設定の場合は DATABASE_URL にフォールバックするが、
#                          本番 DATABASE_URL は Transaction-mode プーラー (:6543) 固定であり
#                          (DEPLOYMENT.md 参照)、プーラー経由の pg_dump は接続断・
#                          機能制限のリスクがあるため警告ログを出す。
#   DATABASE_URL        : フォールバック用。本番運用では DATABASE_URL_DIRECT を設定すること。
#   BACKUP_GCS_BUCKET   : (任意) アップロード先 GCS バケット名 (gs:// 無しのバケット名のみ)。
#                          未設定の場合はローカル/コンテナ内保存のみで GCS アップロードを
#                          スキップする (Cloud Run Jobs 環境ではジョブ終了時にコンテナの
#                          ディスクごと消滅するため、本番運用では必須の設定)。
#                          バケット自体の作成・IAM 設定はこのスクリプトのスコープ外
#                          (別途 HIL で作成すること)。
#
# 出力:
#   ${BACKUP_DIR:-./backups}/oneco_production_<timestamp>.dump.gz
#     pg_dump のカスタムフォーマット (-Fc) を gzip で追加圧縮したファイル。
#     BACKUP_GCS_BUCKET 設定時は gs://${BACKUP_GCS_BUCKET}/oneco_production_backups/ 配下にも
#     同名でアップロードする (Cloud Run Jobs 環境で永続化するための本体)。
#
# 前提:
#   - pg_dump / gzip が実行環境 (Cloud Run Jobs 等) にインストール済みであること
#   - DATABASE_URL_DIRECT (または DATABASE_URL) は SQLAlchemy 形式
#     (postgresql+asyncpg://...) を許容する。
#     pg_dump は "+asyncpg" 等のドライバサフィックスを解釈できないため、
#     このスクリプト内で postgresql:// (libpq URI) に正規化してから使用する。
#   - GCS へのアップロードには gcloud CLI (`gcloud storage cp`) または
#     `gsutil` のいずれかが実行環境にインストール済みであること。
#     どちらも無い場合はアップロードをスキップし警告ログのみ出す (失敗扱いにしない)。
#
# ------------------------------------------------------------------
# RESTORE 手順 (別環境への復元 / 誤 DELETE・誤 migration からのロールバック):
#
#   1. バックアップファイルを展開する:
#        gzip -dk oneco_production_YYYYMMDD_HHMMSS.dump.gz
#
#   2. pg_restore で復元する (--dbname は復元先の接続文字列。
#      pg_dump 同様、pg_restore も Supabase 公式は Direct Connection の使用を
#      推奨しているため、Transaction-mode プーラー (:6543) ではなく
#      Direct Connection (:5432, db.<project>.supabase.co) を使うこと。
#      postgresql+asyncpg:// 形式のままだと pg_restore が解釈できないため
#      本スクリプトと同様に postgresql:// へ書き換えること):
#        pg_restore --clean --if-exists --no-owner --no-privileges \
#          --dbname="postgresql://user:pass@db.<project>.supabase.co:5432/db" \
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
#   - 本番 DATABASE_URL_DIRECT (Direct Connection) でのバックアップ実行はスクリプト
#     作成者の環境では未検証。運用開始前に一度、本番相当の接続文字列でリハーサル実行し、
#     ファイルサイズ・pg_restore --list でのテーブル一覧が妥当か確認すること。
#     (ローカルの使い捨て PostgreSQL コンテナに対しては
#      backup → drop table → pg_restore の一連の流れを検証済み。
#      pg_dump/pg_restore のメジャーバージョンが Supabase 側 PostgreSQL の
#      メジャーバージョンより新しいと、新しい GUC 由来の "SET ... = 0;" 行などで
#      無害な警告が出ることがある。実行環境の pg_dump は Supabase の
#      PostgreSQL バージョンに合わせるか、同等以上のものを使うこと)
#   - GCS へのアップロード (BACKUP_GCS_BUCKET 設定時) も実際のバケットへの書き込みは
#     未検証。運用開始前にバケット作成・IAM 権限付与後、一度実際にアップロードが
#     成功することを確認すること。
#   - Supabase 側で追加の接続オプションが必要な場合、DATABASE_URL_DIRECT の
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
# 接続文字列の優先順位: DATABASE_URL_DIRECT (Direct Connection, 推奨) > DATABASE_URL (フォールバック)。
# Supabase 公式ドキュメントは pg_dump/pg_restore に Direct Connection の使用を明記しており、
# 本番 DATABASE_URL は Transaction-mode プーラー (:6543, DEPLOYMENT.md 参照) 固定のため、
# DATABASE_URL しか無い場合は警告を出しつつフォールバックする (失敗させない)。
if [ -n "${DATABASE_URL_DIRECT:-}" ]; then
    SOURCE_URL="${DATABASE_URL_DIRECT}"
    log_info "DATABASE_URL_DIRECT (Direct Connection) を使用します。"
elif [ -n "${DATABASE_URL:-}" ]; then
    SOURCE_URL="${DATABASE_URL}"
    log_warning "DATABASE_URL_DIRECT が未設定のため DATABASE_URL にフォールバックします。"
    log_warning "本番 DATABASE_URL は Transaction-mode プーラー (:6543) 固定であり、"
    log_warning "Supabase 公式は pg_dump に Direct Connection の使用を推奨しています"
    log_warning "(https://supabase.com/docs/guides/database/connecting-to-postgres)。"
    log_warning "Supabase ダッシュボードで Direct Connection 文字列を取得し、"
    log_warning "DATABASE_URL_DIRECT として設定することを推奨します。"
else
    log_error "DATABASE_URL_DIRECT も DATABASE_URL も未設定です。本番 Supabase の接続文字列を設定してください。"
    exit 1
fi

if ! command -v pg_dump >/dev/null 2>&1; then
    log_error "pg_dump が見つかりません。postgresql-client をインストールしてください。"
    exit 1
fi

# SQLAlchemy 形式 (postgresql+asyncpg://... 等) を pg_dump が解釈できる
# libpq URI (postgresql://...) に正規化する。
PG_DUMP_URL=$(echo "${SOURCE_URL}" | sed -E 's#^postgresql\+[a-zA-Z0-9_]+://#postgresql://#')

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

# --- GCS アップロード ---
# Cloud Run Jobs のコンテナはジョブ終了と同時にディスクごと消滅するため、
# ${BACKUP_DIR} へのローカル出力だけでは実質バックアップが残らない。
# BACKUP_GCS_BUCKET 設定時のみアップロードする。バケット未作成・権限不足・
# gcloud/gsutil 未インストール等はいずれも warning に留め、スクリプト自体は
# 失敗させない (pg_dump によるローカル/コンテナ内バックアップ自体は既に成功しているため)。
GCS_UPLOAD_STATUS="skipped"
if [ -z "${BACKUP_GCS_BUCKET:-}" ]; then
    log_warning "BACKUP_GCS_BUCKET が未設定のため GCS アップロードをスキップします。"
    log_warning "Cloud Run Jobs 環境ではジョブ終了時にコンテナのディスクごと消滅するため、"
    log_warning "本番運用では BACKUP_GCS_BUCKET の設定 (バケット作成・IAM 権限付与は別途対応) が必須です。"
else
    GCS_DEST="gs://${BACKUP_GCS_BUCKET}/oneco_production_backups/$(basename "${GZIP_FILE}")"
    if command -v gcloud >/dev/null 2>&1; then
        log_info "GCS へアップロードします (gcloud storage cp): ${GCS_DEST}"
        if gcloud storage cp "${GZIP_FILE}" "${GCS_DEST}"; then
            GCS_UPLOAD_STATUS="uploaded: ${GCS_DEST}"
            log_success "GCS アップロード完了: ${GCS_DEST}"
        else
            log_warning "GCS アップロードに失敗しました (バケット未作成・権限不足の可能性があります)。"
            log_warning "バケット作成・IAM 権限付与は別途対応してください (このスクリプトのスコープ外)。"
        fi
    elif command -v gsutil >/dev/null 2>&1; then
        log_info "GCS へアップロードします (gsutil cp): ${GCS_DEST}"
        if gsutil cp "${GZIP_FILE}" "${GCS_DEST}"; then
            GCS_UPLOAD_STATUS="uploaded: ${GCS_DEST}"
            log_success "GCS アップロード完了: ${GCS_DEST}"
        else
            log_warning "GCS アップロードに失敗しました (バケット未作成・権限不足の可能性があります)。"
            log_warning "バケット作成・IAM 権限付与は別途対応してください (このスクリプトのスコープ外)。"
        fi
    else
        log_warning "gcloud / gsutil のどちらも見つからないため GCS アップロードをスキップします。"
    fi
fi

# Summary
echo ""
echo "=========================================="
log_success "本番 DB バックアップが完了しました"
echo "  出力先 (ローカル/コンテナ内): ${GZIP_FILE}"
echo "  サイズ: ${GZIP_SIZE}"
echo "  GCS アップロード: ${GCS_UPLOAD_STATUS}"
echo ""
echo "リストア手順はこのファイル冒頭のコメントを参照してください。"
echo "=========================================="
