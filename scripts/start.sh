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

# Start Flask app
echo -e "${GREEN}Starting Flask app...${NC}"
nohup python app.py > logs/flask.log 2>&1 &
FLASK_PID=$!
echo "Flask started (PID: $FLASK_PID)"

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

# Start Vite dev server (frontend)
echo -e "${GREEN}Starting Vite dev server...${NC}"
cd frontend
nohup npm run dev > ../logs/vite.log 2>&1 &
VITE_PID=$!
cd ..
echo "Vite dev server started (PID: $VITE_PID)"

# Save PIDs to file for easy stopping
echo $FLASK_PID > logs/flask.pid
echo $WORKER_PID > logs/worker.pid
echo $BEAT_PID > logs/beat.pid
echo $VITE_PID > logs/vite.pid

echo -e "${BLUE}All services running in background.${NC}"
echo -e "${BLUE}Backend: http://127.0.0.1:3000/{NC}"
echo -e "${BLUE}Frontend: http://localhost:5173${NC}"
echo -e "${BLUE}Logs available in logs/ directory${NC}"
echo -e "${BLUE}To stop services, run: ./stop.sh${NC}"
echo -e "${BLUE}To view logs: tail -f logs/flask.log or logs/vite.log${NC}"