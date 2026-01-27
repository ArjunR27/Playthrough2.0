#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

stop_pid_file() {
    local label=$1
    local pid_file=$2

    if [ -f "$pid_file" ]; then
        local pid
        pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            echo -e "${GREEN}Stopping ${label} (PID: $pid)...${NC}"
            kill "$pid"
        else
            echo -e "${GREEN}${label} not running (stale PID file).${NC}"
        fi
        rm -f "$pid_file"
    else
        echo -e "${GREEN}No ${label} PID file found.${NC}"
    fi
}

echo -e "${GREEN}Stopping Last.fm services...${NC}"

stop_pid_file "Last.fm Flask" "logs/last_fm_flask.pid"
stop_pid_file "Last.fm Celery worker" "logs/last_fm_worker.pid"
stop_pid_file "Last.fm Celery beat" "logs/last_fm_beat.pid"

# Stop Redis
redis-cli shutdown 2>/dev/null
echo -e "${GREEN}Redis stopped${NC}"

echo -e "${BLUE}Done.${NC}"
