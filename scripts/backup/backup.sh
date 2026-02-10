#!/bin/bash
# Database & Files Backup Script
# Usage: ./scripts/backup/backup.sh [--retention-days N]

set -e

# Configuration
BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_DAYS="${1:-7}"
COMPOSE_FILE="docker-compose.prod.yml"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
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

# Create backup directory
BACKUP_PATH="${BACKUP_DIR}/${TIMESTAMP}"
mkdir -p "${BACKUP_PATH}"

log_info "Starting backup process..."
log_info "Backup location: ${BACKUP_PATH}"

# 1. Backup PostgreSQL database
log_info "Backing up PostgreSQL database..."
docker-compose -f ${COMPOSE_FILE} exec -T postgres \
    pg_dump -U oneco -Fc oneco > "${BACKUP_PATH}/database.dump"

# Also create SQL format for easy inspection
docker-compose -f ${COMPOSE_FILE} exec -T postgres \
    pg_dump -U oneco oneco > "${BACKUP_PATH}/database.sql"

DB_SIZE=$(du -h "${BACKUP_PATH}/database.dump" | cut -f1)
log_success "Database backup completed (${DB_SIZE})"

# 2. Backup database schema only
log_info "Backing up database schema..."
docker-compose -f ${COMPOSE_FILE} exec -T postgres \
    pg_dump -U oneco --schema-only oneco > "${BACKUP_PATH}/schema.sql"
log_success "Schema backup completed"

# 3. Backup Redis data
log_info "Backing up Redis data..."
docker-compose -f ${COMPOSE_FILE} exec -T redis \
    redis-cli SAVE > /dev/null

docker run --rm \
    -v oneco_redis-data:/data \
    -v "$(pwd)/${BACKUP_PATH}:/backup" \
    alpine tar czf /backup/redis-data.tar.gz -C /data .

log_success "Redis backup completed"

# 4. Backup Docker volumes
log_info "Backing up Docker volumes..."
docker run --rm \
    -v oneco_postgres-data:/data \
    -v "$(pwd)/${BACKUP_PATH}:/backup" \
    alpine tar czf /backup/postgres-data.tar.gz -C /data .

log_success "Volume backup completed"

# 5. Backup application snapshots
if [ -d "./snapshots" ]; then
    log_info "Backing up application snapshots..."
    cp -r ./snapshots "${BACKUP_PATH}/"
    log_success "Snapshots backup completed"
fi

# 6. Backup application output
if [ -d "./output" ]; then
    log_info "Backing up application output..."
    cp -r ./output "${BACKUP_PATH}/"
    log_success "Output backup completed"
fi

# 7. Create backup metadata
log_info "Creating backup metadata..."
cat > "${BACKUP_PATH}/metadata.json" <<EOF
{
  "timestamp": "$(date -Iseconds)",
  "backup_type": "full",
  "database_size": "$(du -sh ${BACKUP_PATH}/database.dump | cut -f1)",
  "total_size": "$(du -sh ${BACKUP_PATH} | cut -f1)",
  "hostname": "$(hostname)",
  "git_commit": "$(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')"
}
EOF

log_success "Metadata created"

# 8. Compress backup
log_info "Compressing backup..."
tar czf "${BACKUP_DIR}/backup_${TIMESTAMP}.tar.gz" -C "${BACKUP_DIR}" "${TIMESTAMP}"
COMPRESSED_SIZE=$(du -h "${BACKUP_DIR}/backup_${TIMESTAMP}.tar.gz" | cut -f1)
rm -rf "${BACKUP_PATH}"
log_success "Backup compressed (${COMPRESSED_SIZE})"

# 9. Clean old backups
log_info "Cleaning backups older than ${RETENTION_DAYS} days..."
find "${BACKUP_DIR}" -name "backup_*.tar.gz" -mtime +${RETENTION_DAYS} -delete
REMAINING=$(find "${BACKUP_DIR}" -name "backup_*.tar.gz" | wc -l)
log_success "Cleanup completed (${REMAINING} backups remaining)"

# 10. Verify backup
log_info "Verifying backup integrity..."
if tar tzf "${BACKUP_DIR}/backup_${TIMESTAMP}.tar.gz" > /dev/null; then
    log_success "Backup verification passed"
else
    log_warning "Backup verification failed!"
    exit 1
fi

# Summary
echo ""
echo "=========================================="
log_success "Backup completed successfully!"
echo "  Location: ${BACKUP_DIR}/backup_${TIMESTAMP}.tar.gz"
echo "  Size: ${COMPRESSED_SIZE}"
echo ""
echo "Restore command:"
echo "  ./scripts/backup/restore.sh ${BACKUP_DIR}/backup_${TIMESTAMP}.tar.gz"
echo "=========================================="
