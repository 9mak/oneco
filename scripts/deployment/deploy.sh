#!/bin/bash
# Production Deployment Script
# Usage: ./scripts/deployment/deploy.sh [environment]

set -e  # Exit on error
set -u  # Exit on undefined variable

# Configuration
ENVIRONMENT="${1:-production}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
COMPOSE_FILE="docker-compose.prod.yml"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
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

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."

    # Check Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed"
        exit 1
    fi

    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose is not installed"
        exit 1
    fi

    # Check environment file
    if [ ! -f "${PROJECT_ROOT}/.env.${ENVIRONMENT}" ]; then
        log_error "Environment file .env.${ENVIRONMENT} not found"
        log_info "Please create it from .env.production.example"
        exit 1
    fi

    log_success "Prerequisites check passed"
}

# Backup current deployment
backup_current() {
    log_info "Creating backup of current deployment..."

    BACKUP_DIR="${PROJECT_ROOT}/backups/$(date +%Y%m%d_%H%M%S)"
    mkdir -p "${BACKUP_DIR}"

    # Backup database
    if docker-compose -f "${PROJECT_ROOT}/${COMPOSE_FILE}" ps postgres | grep -q Up; then
        log_info "Backing up database..."
        docker-compose -f "${PROJECT_ROOT}/${COMPOSE_FILE}" exec -T postgres \
            pg_dump -U oneco oneco > "${BACKUP_DIR}/database.sql"
        log_success "Database backup created: ${BACKUP_DIR}/database.sql"
    fi

    # Backup volumes
    log_info "Backing up volumes..."
    docker run --rm \
        -v oneco_postgres-data:/data \
        -v "${BACKUP_DIR}:/backup" \
        alpine tar czf /backup/postgres-data.tar.gz /data

    log_success "Backup completed: ${BACKUP_DIR}"
}

# Pull latest images
pull_images() {
    log_info "Pulling latest images..."
    cd "${PROJECT_ROOT}"
    docker-compose -f "${COMPOSE_FILE}" pull
    log_success "Images pulled successfully"
}

# Build application image
build_image() {
    log_info "Building application image..."
    cd "${PROJECT_ROOT}"
    docker-compose -f "${COMPOSE_FILE}" build --no-cache
    log_success "Image built successfully"
}

# Run database migrations
run_migrations() {
    log_info "Running database migrations..."
    cd "${PROJECT_ROOT}"

    # Ensure database is running
    docker-compose -f "${COMPOSE_FILE}" up -d postgres
    sleep 10

    # Run migrations
    docker-compose -f "${COMPOSE_FILE}" run --rm migration
    log_success "Migrations completed successfully"
}

# Start services
start_services() {
    log_info "Starting services..."
    cd "${PROJECT_ROOT}"

    # Start all services
    docker-compose -f "${COMPOSE_FILE}" up -d

    log_success "Services started"
}

# Health check
health_check() {
    log_info "Performing health checks..."

    # Wait for API to be ready
    log_info "Waiting for API to be ready..."
    MAX_ATTEMPTS=30
    ATTEMPT=0

    while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
        if curl -f http://localhost:8000/health &> /dev/null; then
            log_success "API health check passed"
            break
        fi

        ATTEMPT=$((ATTEMPT + 1))
        if [ $ATTEMPT -eq $MAX_ATTEMPTS ]; then
            log_error "API health check failed after ${MAX_ATTEMPTS} attempts"
            show_logs
            exit 1
        fi

        log_info "Attempt ${ATTEMPT}/${MAX_ATTEMPTS}... waiting 5s"
        sleep 5
    done

    # Check database
    log_info "Checking database connection..."
    if docker-compose -f "${PROJECT_ROOT}/${COMPOSE_FILE}" exec -T postgres \
        pg_isready -U oneco &> /dev/null; then
        log_success "Database connection check passed"
    else
        log_error "Database connection check failed"
        exit 1
    fi

    # Check Redis
    log_info "Checking Redis connection..."
    if docker-compose -f "${PROJECT_ROOT}/${COMPOSE_FILE}" exec -T redis \
        redis-cli ping &> /dev/null; then
        log_success "Redis connection check passed"
    else
        log_error "Redis connection check failed"
        exit 1
    fi
}

# Show logs
show_logs() {
    log_info "Recent logs:"
    cd "${PROJECT_ROOT}"
    docker-compose -f "${COMPOSE_FILE}" logs --tail=50 api
}

# Rollback deployment
rollback() {
    log_warning "Rolling back deployment..."
    cd "${PROJECT_ROOT}"

    # Stop current services
    docker-compose -f "${COMPOSE_FILE}" down

    # Restore from latest backup
    LATEST_BACKUP=$(ls -td "${PROJECT_ROOT}/backups"/*/ | head -1)
    if [ -n "${LATEST_BACKUP}" ]; then
        log_info "Restoring from backup: ${LATEST_BACKUP}"

        # Restore database
        if [ -f "${LATEST_BACKUP}/database.sql" ]; then
            docker-compose -f "${COMPOSE_FILE}" up -d postgres
            sleep 10
            docker-compose -f "${COMPOSE_FILE}" exec -T postgres \
                psql -U oneco oneco < "${LATEST_BACKUP}/database.sql"
            log_success "Database restored"
        fi
    fi

    # Restart services
    docker-compose -f "${COMPOSE_FILE}" up -d
    log_warning "Rollback completed"
}

# Main deployment flow
main() {
    log_info "Starting deployment to ${ENVIRONMENT}..."
    echo "==========================================="

    # Check prerequisites
    check_prerequisites

    # Backup current state
    backup_current

    # Build and deploy
    build_image
    run_migrations
    start_services

    # Health checks
    health_check

    # Show status
    echo "==========================================="
    log_success "Deployment completed successfully!"
    echo ""
    log_info "Service URLs:"
    echo "  - API: http://localhost:8000"
    echo "  - API Docs: http://localhost:8000/docs"
    echo "  - Health: http://localhost:8000/health"
    echo ""
    log_info "Useful commands:"
    echo "  - View logs: docker-compose -f ${COMPOSE_FILE} logs -f"
    echo "  - Stop services: docker-compose -f ${COMPOSE_FILE} down"
    echo "  - Restart API: docker-compose -f ${COMPOSE_FILE} restart api"
}

# Handle errors
trap 'log_error "Deployment failed! Run with rollback: ./deploy.sh --rollback"' ERR

# Parse arguments
if [ "${1:-}" = "--rollback" ]; then
    rollback
    exit 0
fi

# Run main deployment
main
