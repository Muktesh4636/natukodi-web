#!/bin/bash

# Load test script for bet placement API
# Tests with 100 concurrent users placing bets

echo "🧪 Starting Bet Placement Load Test"
echo "===================================="
echo ""

# Configuration
HOST="https://gunduata.club"
USERS=100
SPAWN_RATE=10  # Spawn 10 users per second
DURATION="5m"  # Run for 5 minutes
LOCUSTFILE="test_bet_load.py"

# Check if locust is installed
if ! command -v locust &> /dev/null; then
    echo "❌ Locust is not installed. Installing..."
    pip3 install locust
fi

echo "📊 Test Configuration:"
echo "   Host: $HOST"
echo "   Users: $USERS"
echo "   Spawn Rate: $SPAWN_RATE users/second"
echo "   Duration: $DURATION"
echo ""

# Run the load test
echo "🚀 Starting load test..."
locust -f "$LOCUSTFILE" \
    --host="$HOST" \
    --users="$USERS" \
    --spawn-rate="$SPAWN_RATE" \
    --run-time="$DURATION" \
    --headless \
    --html=bet_load_test_report.html \
    --csv=bet_load_test_results

echo ""
echo "✅ Load test completed!"
echo "📄 Report saved to: bet_load_test_report.html"
echo "📊 CSV results saved to: bet_load_test_results_*.csv"
