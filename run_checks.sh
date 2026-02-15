#!/bin/bash
echo "--- DISK SPACE ---" > /Users/pradyumna/apk_of_ata/server_report.txt
sshpass -p "Gunduata@123" ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no root@72.61.254.71 "df -h" >> /Users/pradyumna/apk_of_ata/server_report.txt 2>&1
echo "--- DOCKER PS ---" >> /Users/pradyumna/apk_of_ata/server_report.txt
sshpass -p "Gunduata@123" ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no root@72.61.254.71 "docker ps" >> /Users/pradyumna/apk_of_ata/server_report.txt 2>&1
echo "--- DOCKER COMPOSE PS ---" >> /Users/pradyumna/apk_of_ata/server_report.txt
sshpass -p "Gunduata@123" ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no root@72.61.254.71 "cd /root/apk_of_ata && docker compose ps" >> /Users/pradyumna/apk_of_ata/server_report.txt 2>&1
echo "--- DOCKER LOGS ---" >> /Users/pradyumna/apk_of_ata/server_report.txt
sshpass -p "Gunduata@123" ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no root@72.61.254.71 "docker logs --tail 50 dice_game_web" >> /Users/pradyumna/apk_of_ata/server_report.txt 2>&1
