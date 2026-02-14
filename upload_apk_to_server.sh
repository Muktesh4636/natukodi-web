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
SERVER_IP="72.61.254.71"
PROJECT_DIR_ON_SERVER="~/apk_of_ata"
LOCAL_APK="./android_app/app/build/outputs/apk/debug/app-debug.apk"
LOCAL_APK_ALT="./backend/staticfiles/assets/gundu_ata_latest.apk"

echo -e "${BLUE}=== Uploading APK to Server ===${NC}"
echo ""

# Find the APK file
if [ -f "$LOCAL_APK" ]; then
    APK_FILE="$LOCAL_APK"
    echo -e "${GREEN}Found APK: $APK_FILE${NC}"
elif [ -f "$LOCAL_APK_ALT" ]; then
    APK_FILE="$LOCAL_APK_ALT"
    echo -e "${GREEN}Found APK: $APK_FILE${NC}"
else
    echo -e "${RED}Error: APK file not found${NC}"
    echo "Looking for:"
    echo "  - $LOCAL_APK"
    echo "  - $LOCAL_APK_ALT"
    exit 1
fi

# Get file size
FILE_SIZE=$(ls -lh "$APK_FILE" | awk '{print $5}')
echo -e "${BLUE}File size: $FILE_SIZE${NC}"
echo ""

# Copy to multiple locations on server
echo -e "${YELLOW}Step 1/3: Copying APK to staticfiles/assets/...${NC}"
scp "$APK_FILE" "${SERVER_USER}@${SERVER_IP}:${PROJECT_DIR_ON_SERVER}/backend/staticfiles/assets/gundu_ata_latest.apk" || {
    echo -e "${RED}Failed to copy to staticfiles/assets/${NC}"
    exit 1
}
echo -e "${GREEN}✓ Copied to staticfiles/assets/${NC}"

echo -e "${YELLOW}Step 2/3: Copying APK to staticfiles/apks/...${NC}"
ssh "${SERVER_USER}@${SERVER_IP}" "mkdir -p ${PROJECT_DIR_ON_SERVER}/backend/staticfiles/apks" && \
scp "$APK_FILE" "${SERVER_USER}@${SERVER_IP}:${PROJECT_DIR_ON_SERVER}/backend/staticfiles/apks/gundu_ata_latest.apk" || {
    echo -e "${YELLOW}Warning: Failed to copy to staticfiles/apks/${NC}"
}
echo -e "${GREEN}✓ Copied to staticfiles/apks/${NC}"

echo -e "${YELLOW}Step 3/3: Setting permissions...${NC}"
ssh "${SERVER_USER}@${SERVER_IP}" "chmod 644 ${PROJECT_DIR_ON_SERVER}/backend/staticfiles/assets/gundu_ata_latest.apk ${PROJECT_DIR_ON_SERVER}/backend/staticfiles/apks/gundu_ata_latest.apk 2>/dev/null" || {
    echo -e "${YELLOW}Warning: Failed to set permissions${NC}"
}
echo -e "${GREEN}✓ Permissions set${NC}"

echo ""
echo -e "${GREEN}=== Upload Complete! ===${NC}"
echo ""
echo -e "${BLUE}APK Download URLs:${NC}"
echo -e "  • ${GREEN}https://gunduata.online/api/download/apk/${NC}"
echo -e "  • ${GREEN}https://gunduata.online/api/apk/${NC}"
echo ""
echo -e "${YELLOW}Note: If the download still doesn't work, restart Gunicorn on the server.${NC}"
