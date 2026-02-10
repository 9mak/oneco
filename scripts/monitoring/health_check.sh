#!/bin/bash
# Health Check Script
# Usage: ./scripts/monitoring/health_check.sh [--verbose]

set -e

# Configuration
API_URL="${API_URL:-http://localhost:8000}"
COMPOSE_FILE="docker-compose.prod.yml"
VERBOSE=false

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Parse arguments
if [ "${1:-}" = "--verbose" ]; then
    VERBOSE=true
fi

# Status tracking
ALL_HEALTHY=true

# Check function
check_service() {
    local service_name=$1
    local check_command=$2
    local description=$3

    if [ "$VERBOSE" = true ]; then
        echo "Checking ${description}..."
    fi

    if eval "$check_command" &> /dev/null; then
        echo -e "${GREEN}✓${NC} ${description}"
        return 0
    else
        echo -e "${RED}✗${NC} ${description}"
        ALL_HEALTHY=false
        return 1
    fi
}

echo "=========================================="
echo "Health Check Report - $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="
echo ""

# 1. Check API Health
check_service "api" \
    "curl -f -s ${API_URL}/health" \
    "API Health Endpoint"

# 2. Check API Response Time
if [ "$VERBOSE" = true ]; then
    RESPONSE_TIME=$(curl -o /dev/null -s -w '%{time_total}' ${API_URL}/health || echo "N/A")
    echo "  Response time: ${RESPONSE_TIME}s"
fi

# 3. Check Database Connection
check_service "database" \
    "docker-compose -f ${COMPOSE_FILE} exec -T postgres pg_isready -U oneco" \
    "PostgreSQL Connection"

# 4. Check Database Tables
check_service "database_tables" \
    "docker-compose -f ${COMPOSE_FILE} exec -T postgres psql -U oneco -d oneco -c 'SELECT count(*) FROM animals' | grep -q '[0-9]'" \
    "Database Tables Accessible"

# 5. Check Redis Connection
check_service "redis" \
    "docker-compose -f ${COMPOSE_FILE} exec -T redis redis-cli ping | grep -q PONG" \
    "Redis Connection"

# 6. Check Docker Containers
echo ""
echo "Container Status:"
docker-compose -f ${COMPOSE_FILE} ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"

# 7. Check Disk Space
echo ""
echo "Disk Space:"
df -h / | tail -1 | awk '{printf "  Used: %s / %s (%s)\n", $3, $2, $5}'

DISK_USAGE=$(df / | tail -1 | awk '{print $5}' | sed 's/%//')
if [ "$DISK_USAGE" -gt 80 ]; then
    echo -e "${YELLOW}  Warning: Disk usage is above 80%${NC}"
    ALL_HEALTHY=false
fi

# 8. Check Memory Usage
echo ""
echo "Memory Usage:"
free -h | grep Mem | awk '{printf "  Used: %s / %s\n", $3, $2}'

# 9. Check API Endpoints
if [ "$VERBOSE" = true ]; then
    echo ""
    echo "API Endpoint Tests:"

    # Test animals list
    if curl -f -s "${API_URL}/animals?limit=1" > /dev/null; then
        echo -e "${GREEN}✓${NC} GET /animals"
    else
        echo -e "${RED}✗${NC} GET /animals"
        ALL_HEALTHY=false
    fi

    # Test RSS feed
    if curl -f -s "${API_URL}/feeds/rss?limit=1" > /dev/null; then
        echo -e "${GREEN}✓${NC} GET /feeds/rss"
    else
        echo -e "${RED}✗${NC} GET /feeds/rss"
        ALL_HEALTHY=false
    fi
fi

# 10. Check Recent Logs for Errors
echo ""
echo "Recent Errors (last 5 minutes):"
ERROR_COUNT=$(docker-compose -f ${COMPOSE_FILE} logs --since 5m api 2>&1 | grep -i error | wc -l)
if [ "$ERROR_COUNT" -gt 0 ]; then
    echo -e "${YELLOW}  Found ${ERROR_COUNT} error(s) in logs${NC}"
    if [ "$VERBOSE" = true ]; then
        docker-compose -f ${COMPOSE_FILE} logs --since 5m api 2>&1 | grep -i error | tail -5
    fi
else
    echo -e "${GREEN}  No errors found${NC}"
fi

# Summary
echo ""
echo "=========================================="
if [ "$ALL_HEALTHY" = true ]; then
    echo -e "${GREEN}Overall Status: HEALTHY${NC}"
    exit 0
else
    echo -e "${RED}Overall Status: UNHEALTHY${NC}"
    echo ""
    echo "Troubleshooting:"
    echo "  - Check logs: docker-compose -f ${COMPOSE_FILE} logs -f"
    echo "  - Restart services: docker-compose -f ${COMPOSE_FILE} restart"
    echo "  - View detailed health: ./scripts/monitoring/health_check.sh --verbose"
    exit 1
fi
