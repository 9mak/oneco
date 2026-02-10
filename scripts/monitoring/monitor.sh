#!/bin/bash
# Real-time Monitoring Dashboard
# Usage: ./scripts/monitoring/monitor.sh [--interval N]

INTERVAL="${1:-5}"
COMPOSE_FILE="docker-compose.prod.yml"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Clear screen function
clear_screen() {
    clear
    echo -e "${CYAN}╔════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║           oneco - Production Monitoring Dashboard              ║${NC}"
    echo -e "${CYAN}╚════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  Refresh: ${INTERVAL}s | Press Ctrl+C to exit"
    echo ""
}

# Get container status
get_container_status() {
    local container=$1
    local status=$(docker-compose -f ${COMPOSE_FILE} ps ${container} 2>/dev/null | grep Up | wc -l)
    if [ "$status" -gt 0 ]; then
        echo -e "${GREEN}●${NC} Running"
    else
        echo -e "${RED}●${NC} Stopped"
    fi
}

# Get container stats
get_container_stats() {
    local container=$1
    docker stats ${container} --no-stream --format "CPU: {{.CPUPerc}} | Memory: {{.MemUsage}}" 2>/dev/null || echo "N/A"
}

# Get API metrics
get_api_metrics() {
    local response=$(curl -s http://localhost:8000/health 2>/dev/null)
    if [ -n "$response" ]; then
        echo "$response" | jq -r '
            "Status: \(.status) | " +
            "Uptime: \(.uptime // "N/A") | " +
            "DB: \(if .database.connected then "✓" else "✗" end)"
        ' 2>/dev/null || echo "Connected"
    else
        echo -e "${RED}Not responding${NC}"
    fi
}

# Get database stats
get_db_stats() {
    docker-compose -f ${COMPOSE_FILE} exec -T postgres psql -U oneco -d oneco -t -c "
        SELECT
            'Tables: ' || count(*) || ' | ' ||
            'Animals: ' || (SELECT count(*) FROM animals) || ' | ' ||
            'Size: ' || pg_size_pretty(pg_database_size('oneco'))
        FROM information_schema.tables
        WHERE table_schema = 'public';
    " 2>/dev/null | tr -d '\n' || echo "N/A"
}

# Get Redis stats
get_redis_stats() {
    local info=$(docker-compose -f ${COMPOSE_FILE} exec -T redis redis-cli INFO stats 2>/dev/null)
    local keys=$(docker-compose -f ${COMPOSE_FILE} exec -T redis redis-cli DBSIZE 2>/dev/null)
    local memory=$(docker-compose -f ${COMPOSE_FILE} exec -T redis redis-cli INFO memory 2>/dev/null | grep used_memory_human | cut -d: -f2 | tr -d '\r')
    echo "Keys: ${keys} | Memory: ${memory}"
}

# Get recent logs
get_recent_errors() {
    docker-compose -f ${COMPOSE_FILE} logs --since 1m api 2>&1 | grep -i error | wc -l
}

# Monitor loop
while true; do
    clear_screen

    # Container Status
    echo -e "${BLUE}▶ Container Status${NC}"
    echo "  ├─ API:        $(get_container_status api)"
    echo "  ├─ PostgreSQL: $(get_container_status postgres)"
    echo "  └─ Redis:      $(get_container_status redis)"
    echo ""

    # API Metrics
    echo -e "${BLUE}▶ API Metrics${NC}"
    echo "  $(get_api_metrics)"
    echo ""

    # Resource Usage
    echo -e "${BLUE}▶ Resource Usage${NC}"
    API_STATS=$(get_container_stats oneco-api)
    DB_STATS=$(get_container_stats oneco-postgres)
    REDIS_STATS=$(get_container_stats oneco-redis)
    echo "  ├─ API:    ${API_STATS}"
    echo "  ├─ DB:     ${DB_STATS}"
    echo "  └─ Redis:  ${REDIS_STATS}"
    echo ""

    # Database Statistics
    echo -e "${BLUE}▶ Database Statistics${NC}"
    echo "  $(get_db_stats)"
    echo ""

    # Redis Statistics
    echo -e "${BLUE}▶ Redis Statistics${NC}"
    echo "  $(get_redis_stats)"
    echo ""

    # Recent Errors
    ERROR_COUNT=$(get_recent_errors)
    echo -e "${BLUE}▶ Recent Errors (last minute)${NC}"
    if [ "$ERROR_COUNT" -gt 0 ]; then
        echo -e "  ${RED}⚠ ${ERROR_COUNT} error(s) detected${NC}"
    else
        echo -e "  ${GREEN}✓ No errors${NC}"
    fi
    echo ""

    # System Resources
    echo -e "${BLUE}▶ System Resources${NC}"
    DISK_USAGE=$(df -h / | tail -1 | awk '{print $5}')
    MEM_USAGE=$(free -h | grep Mem | awk '{print $3 "/" $2}')
    LOAD_AVG=$(uptime | awk -F'load average:' '{print $2}' | xargs)
    echo "  ├─ Disk:   ${DISK_USAGE} used"
    echo "  ├─ Memory: ${MEM_USAGE}"
    echo "  └─ Load:   ${LOAD_AVG}"
    echo ""

    # Network Traffic
    echo -e "${BLUE}▶ Recent API Requests (last minute)${NC}"
    REQUEST_COUNT=$(docker-compose -f ${COMPOSE_FILE} logs --since 1m api 2>&1 | grep -c "HTTP/1.1" || echo "0")
    echo "  Requests: ${REQUEST_COUNT}"
    echo ""

    # Quick Actions
    echo -e "${CYAN}Quick Actions:${NC}"
    echo "  h - Health Check | l - View Logs | r - Restart API | q - Quit"
    echo ""

    # Wait for interval or key press
    read -t ${INTERVAL} -n 1 key 2>/dev/null || true

    case $key in
        h)
            ./scripts/monitoring/health_check.sh
            read -p "Press Enter to continue..."
            ;;
        l)
            docker-compose -f ${COMPOSE_FILE} logs --tail=50 -f api
            ;;
        r)
            docker-compose -f ${COMPOSE_FILE} restart api
            echo "API restarted. Press Enter to continue..."
            read
            ;;
        q)
            clear
            echo "Monitoring stopped."
            exit 0
            ;;
    esac
done
