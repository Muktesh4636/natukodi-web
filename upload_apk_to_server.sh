#!/bin/bash

# Script to upload the latest APK to the server
# Usage: ./upload_apk_to_server.sh

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SERVER_USER="root"
SERVER_PASS="Gunduata@123"
PROJECT_DIR_ON_SERVER="/root/apk_of_ata"
SERVERS=("72.61.254.71" "72.61.254.74" "72.62.226.41")
# Gundu_ata_apk-1 (primary source for present)
LOCAL_APK="/Users/pradyumna/Gundu_ata_apk-1/out/Sikwin_UnityUpdate_v49_signed.apk"
LOCAL_APK_LEGACY="/Users/pradyumna/Gundu_ata_apk-1/kotlin/Sikwin_GunduAta_Final_Clean_signed.apk"
LOCAL_APK_ALT="/Users/pradyumna/Gundu_ata_apk-1/out/Sikwin_UnityUpdate_v49.apk"
LOCAL_APK_DEBUG="/Users/pradyumna/Gundu_ata_apk-1/kotlin/Sikwin_GunduAta_Final_Clean.apk"
LOCAL_APK_LEGACY2="./backend/staticfiles/assets/gundu_ata_latest.apk"
LOCAL_APK_LEGACY3="./android_app/Gundu_ata_apk/Gundu Ata 3.apk"

echo -e "${BLUE}=== Uploading APK to Server ===${NC}"
echo ""

# Find the APK file (prefer Gundu_ata_apk-1, then fallbacks)
if [ -f "$LOCAL_APK" ]; then
    APK_FILE="$LOCAL_APK"
    echo -e "${GREEN}Found APK: $APK_FILE${NC}"
elif [ -f "$LOCAL_APK_LEGACY" ]; then
    APK_FILE="$LOCAL_APK_LEGACY"
    echo -e "${GREEN}Found APK: $APK_FILE${NC}"
elif [ -f "$LOCAL_APK_ALT" ]; then
    APK_FILE="$LOCAL_APK_ALT"
    echo -e "${GREEN}Found APK: $APK_FILE${NC}"
elif [ -f "$LOCAL_APK_DEBUG" ]; then
    APK_FILE="$LOCAL_APK_DEBUG"
    echo -e "${GREEN}Found APK: $APK_FILE${NC}"
elif [ -f "$LOCAL_APK_LEGACY2" ]; then
    APK_FILE="$LOCAL_APK_LEGACY2"
    echo -e "${GREEN}Found APK: $APK_FILE${NC}"
elif [ -f "$LOCAL_APK_LEGACY3" ]; then
    APK_FILE="$LOCAL_APK_LEGACY3"
    echo -e "${GREEN}Found APK: $APK_FILE${NC}"
else
    echo -e "${RED}Error: APK file not found${NC}"
    echo "Looking for:"
    echo "  - $LOCAL_APK"
    echo "  - $LOCAL_APK_LEGACY"
    echo "  - $LOCAL_APK_ALT"
    echo "  - $LOCAL_APK_DEBUG"
    echo "  - $LOCAL_APK_LEGACY2"
    echo "  - $LOCAL_APK_LEGACY3"
    exit 1
fi

# Get file size
FILE_SIZE=$(ls -lh "$APK_FILE" | awk '{print $5}')
echo -e "${BLUE}File size: $FILE_SIZE${NC}"
echo ""

# Copy to all production servers
for SERVER_IP in "${SERVERS[@]}"; do
    echo ""
    echo -e "${BLUE}--- Uploading to $SERVER_IP ---${NC}"
    echo -e "${YELLOW}Step 1/3: Copying APK to staticfiles/assets/...${NC}"
    sshpass -p "$SERVER_PASS" scp -o StrictHostKeyChecking=no "$APK_FILE" "${SERVER_USER}@${SERVER_IP}:${PROJECT_DIR_ON_SERVER}/backend/staticfiles/assets/gundu_ata_latest.apk" || {
        echo -e "${RED}Failed to copy to $SERVER_IP staticfiles/assets/${NC}"
        continue
    }
    echo -e "${GREEN}✓ Copied to staticfiles/assets${NC}"

    echo -e "${YELLOW}Step 2/3: Copying APK to staticfiles/apks/...${NC}"
    sshpass -p "$SERVER_PASS" ssh -o StrictHostKeyChecking=no "${SERVER_USER}@${SERVER_IP}" "mkdir -p ${PROJECT_DIR_ON_SERVER}/backend/staticfiles/apks" && \
    sshpass -p "$SERVER_PASS" scp -o StrictHostKeyChecking=no "$APK_FILE" "${SERVER_USER}@${SERVER_IP}:${PROJECT_DIR_ON_SERVER}/backend/staticfiles/apks/gundu_ata_latest.apk" || {
        echo -e "${YELLOW}Warning: Failed to copy to staticfiles/apks/${NC}"
    }
    echo -e "${GREEN}✓ Copied to staticfiles/apks${NC}"

    echo -e "${YELLOW}Step 3/3: Setting permissions...${NC}"
    sshpass -p "$SERVER_PASS" ssh -o StrictHostKeyChecking=no "${SERVER_USER}@${SERVER_IP}" "chmod 644 ${PROJECT_DIR_ON_SERVER}/backend/staticfiles/assets/gundu_ata_latest.apk ${PROJECT_DIR_ON_SERVER}/backend/staticfiles/apks/gundu_ata_latest.apk 2>/dev/null" || {
        echo -e "${YELLOW}Warning: Failed to set permissions${NC}"
    }
    echo -e "${YELLOW}Step 4/4: Rebuilding web container to pick up new APK...${NC}"
    sshpass -p "$SERVER_PASS" ssh -o StrictHostKeyChecking=no "${SERVER_USER}@${SERVER_IP}" "cd ${PROJECT_DIR_ON_SERVER} && docker compose up -d --build web" || {
        echo -e "${YELLOW}Warning: Rebuild failed, container may still serve old APK${NC}"
    }
    echo -e "${GREEN}✓ Server $SERVER_IP done${NC}"
done

echo ""
echo -e "${GREEN}=== Upload Complete! ===${NC}"
echo ""
echo -e "${BLUE}APK Download URLs:${NC}"
echo -e "  • ${GREEN}https://gunduata.club/api/download/apk/${NC}"
echo -e "  • ${GREEN}https://gunduata.club/api/apk/${NC}"
echo ""
echo -e "${YELLOW}Note: If the download still doesn't work, restart Gunicorn on the server.${NC}"
