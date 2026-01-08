#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting all services in background...${NC}"

# Create logs directory if it doesn't exist
mkdir -p logs

# Start Redis server
echo -e "${GREEN}Starting Redis server...${NC}"
redis-server --daemonize yes

# Give Redis a moment to start
sleep 2

# Next.js config
NEXT_HOST="127.0.0.1"
NEXT_PORT="8080"

# Start Flask app
echo -e "${GREEN}Starting Flask app...${NC}"
nohup python app.py > logs/flask.log 2>&1 &
FLASK_PID=$!
echo "Flask started (PID: $FLASK_PID)"

# Start Next.js frontend
if [ -d frontend ]; then
    echo -e "${GREEN}Starting Next.js frontend...${NC}"
    pushd frontend >/dev/null
    nohup npm run dev -- --hostname "$NEXT_HOST" --port "$NEXT_PORT" > ../logs/next.log 2>&1 &
    NEXT_PID=$!
    popd >/dev/null
    echo "Next.js started (PID: $NEXT_PID)"
else
    echo -e "${GREEN}frontend/ not found; skipping Next.js startup.${NC}"
fi

# Start Celery worker
echo -e "${GREEN}Starting Celery worker...${NC}"
nohup celery -A album_tracking worker --loglevel=info > logs/celery_worker.log 2>&1 &
WORKER_PID=$!
echo "Celery worker started (PID: $WORKER_PID)"

# Start Celery beat
echo -e "${GREEN}Starting Celery beat...${NC}"
nohup celery -A album_tracking beat --loglevel=info > logs/celery_beat.log 2>&1 &
BEAT_PID=$!
echo "Celery beat started (PID: $BEAT_PID)"

# Save PIDs to file for easy stopping
echo $FLASK_PID > logs/flask.pid
echo $WORKER_PID > logs/worker.pid
echo $BEAT_PID > logs/beat.pid
if [ -n "$NEXT_PID" ]; then
    echo $NEXT_PID > logs/next.pid
fi

echo -e "${BLUE}All services running in background.${NC}"
echo -e "${BLUE}Backend: http://127.0.0.1:3000${NC}"
echo -e "${BLUE}Frontend: http://${NEXT_HOST}:${NEXT_PORT}${NC}"
echo -e "${BLUE}Logs available in logs/ directory${NC}"
echo -e "${BLUE}To stop services, run: ./stop.sh${NC}"
echo -e "${BLUE}To view logs: tail -f logs/flask.log or logs/next.log${NC}"
