#!/bin/bash

# Test Load Balancer with Multiple Connections

echo "🧪 Testing Load Balancer with 10 Simulated Users..."
echo ""

LB_SERVER="72.61.254.71"
PASSWORD="Gunduata@123"

# Test 1: Check backend servers directly
echo "1. Checking Backend Servers:"
echo "   Server 1 (72.61.254.71:8001):"
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@$LB_SERVER "curl -s -o /dev/null -w '   Status: %{http_code}\n' http://72.61.254.71:8001/api/game/round/ 2>&1"

echo "   Server 2 (72.61.254.74:8001):"
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@$LB_SERVER "curl -s -o /dev/null -w '   Status: %{http_code}\n' http://72.61.254.74:8001/api/game/round/ 2>&1"

echo ""
echo "2. Testing Load Balancer Distribution (10 requests):"
echo "   Making 10 requests through load balancer..."

# Make 10 requests and track which server responds
for i in {1..10}; do
    RESPONSE=$(sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@$LB_SERVER "curl -s -I http://localhost/api/game/round/ 2>&1 | grep -i 'server\|x-real-ip\|via' | head -1")
    echo "   Request $i: $RESPONSE"
done

echo ""
echo "3. Checking Nginx Access Logs (last 10 entries):"
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@$LB_SERVER "tail -10 /var/log/nginx/access.log 2>/dev/null | awk '{print \$1, \$7}' | tail -5 || echo '   Logs not available'"

echo ""
echo "4. Load Balancer Health Check:"
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@$LB_SERVER "curl -s http://localhost/health && echo ''"

echo ""
echo "✅ Load balancer test complete!"
