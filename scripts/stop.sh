#!/bin/bash

# Colors for output
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${RED}Stopping all services...${NC}"

# Stop Flask
if [ -f logs/flask.pid ]; then
    kill $(cat logs/flask.pid) 2>/dev/null
    rm logs/flask.pid
    echo "Flask stopped"
fi

# Stop Celery worker
if [ -f logs/worker.pid ]; then
    kill $(cat logs/worker.pid) 2>/dev/null
    rm logs/worker.pid
    echo "Celery worker stopped"
fi

# Stop Celery beat
if [ -f logs/beat.pid ]; then
    kill $(cat logs/beat.pid) 2>/dev/null
    rm logs/beat.pid
    echo "Celery beat stopped"
fi

# Stop Next.js
if [ -f logs/next.pid ]; then
    kill $(cat logs/next.pid) 2>/dev/null
    rm logs/next.pid
    echo "Next.js stopped"
fi

# Stop Redis
redis-cli shutdown 2>/dev/null
echo "Redis stopped"

echo -e "${BLUE}All services stopped${NC}"
