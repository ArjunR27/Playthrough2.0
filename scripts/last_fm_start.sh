#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting Last.fm services in background...${NC}"

# Create logs directory if it doesn't exist
mkdir -p logs

# Start Redis server
echo -e "${GREEN}Starting Redis server...${NC}"
redis-server --daemonize yes

# Give Redis a moment to start
sleep 2

# Start Last.fm Flask app
if [ -d backend ]; then
    echo -e "${GREEN}Starting Last.fm Flask app...${NC}"
    PORT="3001" PYTHONPATH=backend nohup python -m last_fm_backend > logs/last_fm_flask.log 2>&1 &
    FLASK_PID=$!
    echo "Last.fm Flask started (PID: $FLASK_PID)"
else
    echo -e "${GREEN}backend/ not found; skipping Flask startup.${NC}"
fi

# Start Last.fm Celery worker
if [ -d backend ]; then
    echo -e "${GREEN}Starting Last.fm Celery worker...${NC}"
    PYTHONPATH=backend nohup celery -A last_fm_album_tracking worker --loglevel=info > logs/last_fm_celery_worker.log 2>&1 &
    WORKER_PID=$!
    echo "Last.fm Celery worker started (PID: $WORKER_PID)"
else
    echo -e "${GREEN}backend/ not found; skipping Celery worker.${NC}"
fi

# Start Last.fm Celery beat
if [ -d backend ]; then
    echo -e "${GREEN}Starting Last.fm Celery beat...${NC}"
    PYTHONPATH=backend nohup celery -A last_fm_album_tracking beat --loglevel=info > logs/last_fm_celery_beat.log 2>&1 &
    BEAT_PID=$!
    echo "Last.fm Celery beat started (PID: $BEAT_PID)"
else
    echo -e "${GREEN}backend/ not found; skipping Celery beat.${NC}"
fi

# Save PIDs to file for easy stopping
if [ -n "$FLASK_PID" ]; then
    echo $FLASK_PID > logs/last_fm_flask.pid
fi
if [ -n "$WORKER_PID" ]; then
    echo $WORKER_PID > logs/last_fm_worker.pid
fi
if [ -n "$BEAT_PID" ]; then
    echo $BEAT_PID > logs/last_fm_beat.pid
fi

echo -e "${BLUE}Last.fm services running in background.${NC}"
echo -e "${BLUE}Backend: http://127.0.0.1:3001${NC}"
echo -e "${BLUE}Logs available in logs/ directory${NC}"
echo -e "${BLUE}To stop services, run: ./stop.sh${NC}"
echo -e "${BLUE}To view logs: tail -f logs/last_fm_flask.log${NC}"
