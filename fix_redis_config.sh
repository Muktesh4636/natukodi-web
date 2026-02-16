#!/bin/bash

# Script to fix Redis configuration on all servers
# Correct Redis: 72.61.254.74 with password Gunduata@123

PASSWORD="Gunduata@123"
SERVERS=("72.61.254.71" "72.61.254.74" "72.62.226.41")
REDIS_HOST="72.61.254.74"
REDIS_PASSWORD="Gunduata@123"

echo "🛠️ Fixing Redis configuration on all servers..."

for SERVER in "${SERVERS[@]}"; do
    echo "--------------------------------------------------"
    echo "📦 Processing Server: $SERVER"
    
    # Update REDIS_HOST and add REDIS_PASSWORD if missing
    sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@$SERVER << EOF
        cd /root/apk_of_ata
        
        # 1. Update REDIS_HOST to correct IP
        sed -i 's/REDIS_HOST=.*/REDIS_HOST=$REDIS_HOST/g' docker-compose.yml
        
        # 2. Add REDIS_PASSWORD after REDIS_HOST if not present
        if ! grep -q "REDIS_PASSWORD" docker-compose.yml; then
            sed -i "/REDIS_HOST=$REDIS_HOST/a \      - REDIS_PASSWORD=$REDIS_PASSWORD" docker-compose.yml
        else
            sed -i "s/REDIS_PASSWORD=.*/REDIS_PASSWORD=$REDIS_PASSWORD/g" docker-compose.yml
        fi
        
        # 3. Restart services
        echo "🔄 Restarting Docker services on \$SERVER..."
        docker compose up -d
        
        echo "✅ Server \$SERVER updated and services started."
EOF
done

echo "--------------------------------------------------"
echo "🎉 Redis configuration fix complete!"
echo "Monitoring logs for 10 seconds..."
sleep 5
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@72.61.254.71 "docker logs --tail 20 dice_game_web"
