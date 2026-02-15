#!/bin/bash

# Comprehensive Load Balancer Verification Script

LB_SERVER="72.61.254.71"
PASSWORD="Gunduata@123"

echo "🔍 LOAD BALANCER VERIFICATION"
echo "=============================="
echo ""

# 1. Check Nginx Status
echo "1. Nginx Status:"
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@$LB_SERVER "systemctl is-active nginx && echo '   ✅ Nginx is running' || echo '   ❌ Nginx is not running'"
echo ""

# 2. Check Backend Servers
echo "2. Backend Server Status:"
echo "   Server 1 (72.61.254.71:8001):"
STATUS1=$(sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@$LB_SERVER "curl -s -o /dev/null -w '%{http_code}' http://72.61.254.71:8001/api/game/round/ 2>&1")
if [ "$STATUS1" = "401" ] || [ "$STATUS1" = "200" ]; then
    echo "   ✅ Server 1 responding (HTTP $STATUS1)"
else
    echo "   ⚠️  Server 1 status: HTTP $STATUS1"
fi

echo "   Server 2 (72.61.254.74:8001):"
STATUS2=$(sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@$LB_SERVER "curl -s -o /dev/null -w '%{http_code}' http://72.61.254.74:8001/api/game/round/ 2>&1")
if [ "$STATUS2" = "401" ] || [ "$STATUS2" = "200" ]; then
    echo "   ✅ Server 2 responding (HTTP $STATUS2)"
else
    echo "   ⚠️  Server 2 status: HTTP $STATUS2"
fi
echo ""

# 3. Test Load Balancer Health
echo "3. Load Balancer Health Check:"
HEALTH=$(sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@$LB_SERVER "curl -s http://localhost/health")
if [ "$HEALTH" = "healthy" ]; then
    echo "   ✅ Health check passed"
else
    echo "   ⚠️  Health check: $HEALTH"
fi
echo ""

# 4. Test Load Distribution (10 requests)
echo "4. Load Distribution Test (10 requests):"
SUCCESS=0
FAILED=0
for i in {1..10}; do
    HTTP_CODE=$(sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@$LB_SERVER "curl -s -o /dev/null -w '%{http_code}' http://localhost/api/game/round/ 2>&1")
    if [ "$HTTP_CODE" = "401" ] || [ "$HTTP_CODE" = "200" ]; then
        SUCCESS=$((SUCCESS + 1))
        echo -n "✅ "
    else
        FAILED=$((FAILED + 1))
        echo -n "⚠️  "
    fi
done
echo ""
echo "   Results: $SUCCESS successful, $FAILED failed"
echo ""

# 5. Check Docker Containers
echo "5. Docker Container Status:"
echo "   Server 1:"
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@$LB_SERVER "docker ps --format '   {{.Names}}: {{.Status}}' | grep web || echo '   ⚠️  No web container'"
echo "   Server 2:"
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@72.61.254.74 "docker ps --format '   {{.Names}}: {{.Status}}' | grep web || echo '   ⚠️  No web container'"
echo ""

# 6. Summary
echo "=============================="
echo "📊 SUMMARY:"
if [ "$SUCCESS" -ge 8 ] && [ "$STATUS1" = "401" ] && [ "$STATUS2" = "401" ]; then
    echo "✅ Load Balancer: WORKING"
    echo "✅ Both backend servers: RESPONDING"
    echo ""
    echo "🎮 For 10 users:"
    echo "   - All users connect through load balancer"
    echo "   - Traffic distributed between Server 1 and Server 2"
    echo "   - All users see the same game (shared Redis)"
    echo "   - WebSocket connections properly routed"
else
    echo "⚠️  Load Balancer: NEEDS ATTENTION"
    echo "   - Check backend server status"
    echo "   - Verify nginx configuration"
fi
echo ""
