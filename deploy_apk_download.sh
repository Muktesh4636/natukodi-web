#!/bin/bash

# Script to deploy APK download functionality
# Copies only the modified files and restarts the service

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
LOCAL_BACKEND_DIR="./backend"

echo -e "${BLUE}=== Deploying APK Download Feature ===${NC}"
echo ""

# Check if files exist locally
if [ ! -f "${LOCAL_BACKEND_DIR}/dice_game/urls.py" ]; then
    echo -e "${RED}Error: ${LOCAL_BACKEND_DIR}/dice_game/urls.py not found${NC}"
    exit 1
fi

if [ ! -f "${LOCAL_BACKEND_DIR}/dice_game/views.py" ]; then
    echo -e "${RED}Error: ${LOCAL_BACKEND_DIR}/dice_game/views.py not found${NC}"
    exit 1
fi

echo -e "${YELLOW}Step 1/3: Copying urls.py...${NC}"
scp "${LOCAL_BACKEND_DIR}/dice_game/urls.py" "${SERVER_USER}@${SERVER_IP}:${PROJECT_DIR_ON_SERVER}/backend/dice_game/urls.py" || {
    echo -e "${RED}Failed to copy urls.py${NC}"
    exit 1
}
echo -e "${GREEN}✓ urls.py copied${NC}"

echo -e "${YELLOW}Step 2/3: Copying views.py...${NC}"
scp "${LOCAL_BACKEND_DIR}/dice_game/views.py" "${SERVER_USER}@${SERVER_IP}:${PROJECT_DIR_ON_SERVER}/backend/dice_game/views.py" || {
    echo -e "${RED}Failed to copy views.py${NC}"
    exit 1
}
echo -e "${GREEN}✓ views.py copied${NC}"

echo -e "${YELLOW}Step 3/3: Restarting Django service...${NC}"
echo -e "${BLUE}Trying multiple restart methods...${NC}"

# Try docker compose (newer syntax)
ssh "${SERVER_USER}@${SERVER_IP}" "cd ${PROJECT_DIR_ON_SERVER} && docker compose restart web 2>/dev/null" && {
    echo -e "${GREEN}✓ Service restarted with 'docker compose'${NC}"
} || {
    # Try docker-compose (older syntax)
    ssh "${SERVER_USER}@${SERVER_IP}" "cd ${PROJECT_DIR_ON_SERVER} && docker-compose restart web 2>/dev/null" && {
        echo -e "${GREEN}✓ Service restarted with 'docker-compose'${NC}"
    } || {
        # Try systemctl
        ssh "${SERVER_USER}@${SERVER_IP}" "systemctl restart gunicorn 2>/dev/null" && {
            echo -e "${GREEN}✓ Service restarted with 'systemctl'${NC}"
        } || {
            # Try supervisorctl
            ssh "${SERVER_USER}@${SERVER_IP}" "supervisorctl restart web 2>/dev/null" && {
                echo -e "${GREEN}✓ Service restarted with 'supervisorctl'${NC}"
            } || {
                echo -e "${YELLOW}⚠ Could not automatically restart service.${NC}"
                echo -e "${YELLOW}Please restart manually using one of these commands:${NC}"
                echo -e "  ${BLUE}docker compose restart web${NC}"
                echo -e "  ${BLUE}docker-compose restart web${NC}"
                echo -e "  ${BLUE}systemctl restart gunicorn${NC}"
                echo -e "  ${BLUE}supervisorctl restart web${NC}"
                echo -e "  ${BLUE}Or restart the entire container/service${NC}"
            }
        }
    }
}

echo ""
echo -e "${GREEN}=== Deployment Complete! ===${NC}"
echo ""
echo -e "${BLUE}APK Download URLs:${NC}"
echo -e "  • ${GREEN}https://gunduata.online/api/download/apk/${NC}"
echo -e "  • ${GREEN}https://gunduata.online/api/apk/${NC}"
echo -e "  • ${GREEN}https://gunduata.online/gundu-ata.apk${NC}"
echo ""
echo -e "${YELLOW}Note: Wait a few seconds for the service to fully restart before testing.${NC}"
