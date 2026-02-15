#!/bin/bash
echo "Starting server check..." > /Users/pradyumna/apk_of_ata/server_check.log
echo "--- LOGIN API ON SERVER ---" >> /Users/pradyumna/apk_of_ata/server_check.log
sshpass -p "Gunduata@123" ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no root@72.61.254.71 "grep -A 20 'def login' /root/apk_of_ata/backend/accounts/views.py" >> /Users/pradyumna/apk_of_ata/server_check.log 2>&1
echo "--- DOCKER STATUS ---" >> /Users/pradyumna/apk_of_ata/server_check.log
sshpass -p "Gunduata@123" ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no root@72.61.254.71 "docker ps" >> /Users/pradyumna/apk_of_ata/server_check.log 2>&1
echo "--- RECENT LOGS ---" >> /Users/pradyumna/apk_of_ata/server_check.log
sshpass -p "Gunduata@123" ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no root@72.61.254.71 "docker logs --tail 50 dice_game_web" >> /Users/pradyumna/apk_of_ata/server_check.log 2>&1
echo "Done." >> /Users/pradyumna/apk_of_ata/server_check.log
