#!/bin/bash

# Restart all game services
# Usage: ./restart_services.sh

cd "$(dirname "$0")"

echo "🛑 Stopping all services..."
pkill -f "game_engine_v2.py" 2>/dev/null
pkill -f "round_worker.py" 2>/dev/null
pkill -f "start_game_timer" 2>/dev/null
pkill -f "daphne -b 0.0.0.0 -p 8080 dice_game.asgi:application" 2>/dev/null
pkill -f "manage.py runserver" 2>/dev/null
sleep 2

echo "✅ Services stopped"
echo ""
echo "🚀 Starting services..."

# Activate virtual environment
source venv/bin/activate

# Create logs directory if it doesn't exist
mkdir -p logs

# Start game timer in background with logs
echo "Starting game timer..."
python3 manage.py start_game_timer >> logs/game_timer.log 2>&1 &

# Start ASGI server (Daphne) in background with logs
echo "Starting Daphne ASGI server on port 8080..."
AUTOBAHN_USE_NVX=0 daphne -b 0.0.0.0 -p 8080 dice_game.asgi:application >> logs/django_server.log 2>&1 &

# Start New Game Engine (v2) in background
echo "Starting Game Engine v2..."
python3 game_engine_v2.py >> logs/game_engine_v2.log 2>&1 &

# Start Round Worker in background
echo "Starting Round Worker..."
python3 round_worker.py >> logs/round_worker.log 2>&1 &

sleep 3

# Verify services are running
TIMER_COUNT=$(ps aux | grep -E "game_engine_v2.py" | grep -v grep | wc -l | tr -d ' ')
SERVER_COUNT=$(ps aux | grep -E "daphne -b 0.0.0.0 -p 8080 dice_game.asgi:application" | grep -v grep | wc -l | tr -d ' ')
WORKER_COUNT=$(ps aux | grep -E "round_worker.py" | grep -v grep | wc -l | tr -d ' ')

if [ "$TIMER_COUNT" -gt 0 ] && [ "$SERVER_COUNT" -gt 0 ] && [ "$WORKER_COUNT" -gt 0 ]; then
    echo "✅ All services restarted successfully!"
    echo "   - Game Engine v2: Running"
    echo "   - Daphne ASGI Server: Running on port 8080"
    echo "   - Round Worker: Running"
else
    echo "⚠️  Warning: Some services may not have started properly"
    echo "   - Game Engine v2 processes: $TIMER_COUNT"
    echo "   - Django Server processes: $SERVER_COUNT"
    echo "   - Round Worker processes: $WORKER_COUNT"
fi

