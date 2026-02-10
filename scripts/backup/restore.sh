#!/bin/bash
# Restore Backup Script
# Usage: ./scripts/backup/restore.sh <backup_file.tar.gz>

set -e

# Check arguments
if [ $# -eq 0 ]; then
    echo "Usage: $0 <backup_file.tar.gz>"
    echo "Example: $0 ./backups/backup_20260210_120000.tar.gz"
    exit 1
fi

BACKUP_FILE="$1"
COMPOSE_FILE="docker-compose.prod.yml"
RESTORE_DIR="/tmp/oneco_restore_$$"

# Colors
RED='\033[0;31m'
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

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Verify backup file exists
if [ ! -f "${BACKUP_FILE}" ]; then
    log_error "Backup file not found: ${BACKUP_FILE}"
    exit 1
fi

log_warning "=========================================="
log_warning "RESTORE OPERATION"
log_warning "=========================================="
log_warning "This will OVERWRITE current data!"
log_warning "Backup file: ${BACKUP_FILE}"
echo ""
read -p "Are you sure you want to continue? (yes/no): " -r
if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    log_info "Restore cancelled"
    exit 0
fi

# Extract backup
log_info "Extracting backup..."
mkdir -p "${RESTORE_DIR}"
tar xzf "${BACKUP_FILE}" -C "${RESTORE_DIR}"
BACKUP_NAME=$(tar tzf "${BACKUP_FILE}" | head -1 | cut -d/ -f1)
BACKUP_PATH="${RESTORE_DIR}/${BACKUP_NAME}"

if [ ! -d "${BACKUP_PATH}" ]; then
    log_error "Invalid backup structure"
    rm -rf "${RESTORE_DIR}"
    exit 1
fi

log_success "Backup extracted to ${BACKUP_PATH}"

# Show backup metadata
if [ -f "${BACKUP_PATH}/metadata.json" ]; then
    log_info "Backup metadata:"
    cat "${BACKUP_PATH}/metadata.json"
    echo ""
fi

# Stop services
log_info "Stopping services..."
docker-compose -f ${COMPOSE_FILE} down
log_success "Services stopped"

# Restore PostgreSQL database
log_info "Restoring PostgreSQL database..."
docker-compose -f ${COMPOSE_FILE} up -d postgres
sleep 10

# Drop and recreate database
docker-compose -f ${COMPOSE_FILE} exec -T postgres \
    psql -U oneco -c "DROP DATABASE IF EXISTS oneco;"
docker-compose -f ${COMPOSE_FILE} exec -T postgres \
    psql -U oneco -c "CREATE DATABASE oneco;"

# Restore from dump
if [ -f "${BACKUP_PATH}/database.dump" ]; then
    docker-compose -f ${COMPOSE_FILE} exec -T postgres \
        pg_restore -U oneco -d oneco < "${BACKUP_PATH}/database.dump"
    log_success "Database restored from binary dump"
elif [ -f "${BACKUP_PATH}/database.sql" ]; then
    docker-compose -f ${COMPOSE_FILE} exec -T postgres \
        psql -U oneco oneco < "${BACKUP_PATH}/database.sql"
    log_success "Database restored from SQL dump"
else
    log_error "No database backup found"
    exit 1
fi

# Restore Redis data
if [ -f "${BACKUP_PATH}/redis-data.tar.gz" ]; then
    log_info "Restoring Redis data..."
    docker run --rm \
        -v oneco_redis-data:/data \
        -v "$(pwd)/${BACKUP_PATH}:/backup" \
        alpine sh -c "cd /data && tar xzf /backup/redis-data.tar.gz"
    log_success "Redis data restored"
fi

# Restore snapshots
if [ -d "${BACKUP_PATH}/snapshots" ]; then
    log_info "Restoring snapshots..."
    rm -rf ./snapshots
    cp -r "${BACKUP_PATH}/snapshots" ./
    log_success "Snapshots restored"
fi

# Restore output
if [ -d "${BACKUP_PATH}/output" ]; then
    log_info "Restoring output..."
    rm -rf ./output
    cp -r "${BACKUP_PATH}/output" ./
    log_success "Output restored"
fi

# Cleanup
log_info "Cleaning up temporary files..."
rm -rf "${RESTORE_DIR}"
log_success "Cleanup completed"

# Restart all services
log_info "Starting services..."
docker-compose -f ${COMPOSE_FILE} up -d
sleep 15

# Verify restoration
log_info "Verifying restoration..."

# Check database
RECORD_COUNT=$(docker-compose -f ${COMPOSE_FILE} exec -T postgres \
    psql -U oneco -d oneco -t -c "SELECT count(*) FROM animals;" | tr -d ' ')

log_success "Database verification: ${RECORD_COUNT} records in animals table"

# Health check
if curl -f -s http://localhost:8000/health > /dev/null; then
    log_success "API health check passed"
else
    log_warning "API health check failed - service may still be starting"
fi

# Summary
echo ""
echo "=========================================="
log_success "Restore completed successfully!"
echo ""
log_info "Next steps:"
echo "  1. Verify data: curl http://localhost:8000/animals?limit=10"
echo "  2. Check logs: docker-compose -f ${COMPOSE_FILE} logs -f"
echo "  3. Run health check: ./scripts/monitoring/health_check.sh"
echo "=========================================="
