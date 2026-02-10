#!/bin/bash

# One-command deployment script with automatic password handling
# Usage: ./deploy_one_command.sh

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
SERVER_USER="root"
SERVER_IP="72.61.254.71"
SERVER_PASSWORD="Gunduata@123"
PROJECT_DIR_ON_SERVER="~/apk_of_ata"

echo -e "${BLUE}=== Gundu Ata One-Command Deployment ===${NC}"
echo ""

# Check if we're in the right directory
if [ ! -f "docker-compose.yml" ] || [ ! -d "backend" ]; then
    echo -e "${RED}Error: Please run this script from the project root directory${NC}"
    exit 1
fi

# Function to check if SSH key auth works
check_ssh_key() {
    ssh -o BatchMode=yes -o ConnectTimeout=5 ${SERVER_USER}@${SERVER_IP} "echo ok" 2>/dev/null
}

# Function to deploy with SSH keys
deploy_ssh_key() {
    echo -e "${GREEN}✓ Using SSH key authentication${NC}"
    
    echo -e "${YELLOW}Copying files...${NC}"
    scp -q docker-compose.yml ${SERVER_USER}@${SERVER_IP}:${PROJECT_DIR_ON_SERVER}/
    
    echo -e "${YELLOW}Copying backend directory...${NC}"
    rsync -avz --progress \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='.pytest_cache' \
        --exclude='venv' \
        --exclude='env' \
        --exclude='db.sqlite3' \
        --exclude='*.log' \
        backend/ ${SERVER_USER}@${SERVER_IP}:${PROJECT_DIR_ON_SERVER}/backend/ 2>/dev/null || \
    scp -r backend ${SERVER_USER}@${SERVER_IP}:${PROJECT_DIR_ON_SERVER}/
    
    echo -e "${YELLOW}Restarting containers...${NC}"
    ssh ${SERVER_USER}@${SERVER_IP} "cd ${PROJECT_DIR_ON_SERVER} && docker compose down && docker compose up -d --build && sleep 5 && docker compose ps"
    
    echo -e "${GREEN}✅ Deployment complete!${NC}"
}

# Function to deploy with password using expect
deploy_with_expect() {
    echo -e "${YELLOW}Using password authentication (automated)${NC}"
    
    expect << EOF
set timeout 300
spawn scp docker-compose.yml ${SERVER_USER}@${SERVER_IP}:${PROJECT_DIR_ON_SERVER}/
expect {
    "password:" {
        send "${SERVER_PASSWORD}\r"
        exp_continue
    }
    "yes/no" {
        send "yes\r"
        exp_continue
    }
    eof
}

spawn scp -r backend ${SERVER_USER}@${SERVER_IP}:${PROJECT_DIR_ON_SERVER}/
expect {
    "password:" {
        send "${SERVER_PASSWORD}\r"
        exp_continue
    }
    eof
}

spawn ssh ${SERVER_USER}@${SERVER_IP} "cd ${PROJECT_DIR_ON_SERVER} && docker compose down && docker compose up -d --build && sleep 5 && docker compose ps"
expect {
    "password:" {
        send "${SERVER_PASSWORD}\r"
        exp_continue
    }
    "yes/no" {
        send "yes\r"
        exp_continue
    }
    eof
}
EOF

    echo -e "${GREEN}✅ Deployment complete!${NC}"
}

# Function to deploy with password using sshpass
deploy_with_sshpass() {
    echo -e "${YELLOW}Using password authentication (sshpass)${NC}"
    
    export SSHPASS=${SERVER_PASSWORD}
    
    sshpass -e scp docker-compose.yml ${SERVER_USER}@${SERVER_IP}:${PROJECT_DIR_ON_SERVER}/
    sshpass -e scp -r backend ${SERVER_USER}@${SERVER_IP}:${PROJECT_DIR_ON_SERVER}/
    sshpass -e ssh ${SERVER_USER}@${SERVER_IP} "cd ${PROJECT_DIR_ON_SERVER} && docker compose down && docker compose up -d --build && sleep 5 && docker compose ps"
    
    echo -e "${GREEN}✅ Deployment complete!${NC}"
}

# Function to deploy with manual password entry
deploy_manual() {
    echo -e "${YELLOW}Manual password authentication${NC}"
    echo -e "${BLUE}You will be prompted for password: ${SERVER_PASSWORD}${NC}"
    echo ""
    
    scp docker-compose.yml ${SERVER_USER}@${SERVER_IP}:${PROJECT_DIR_ON_SERVER}/
    scp -r backend ${SERVER_USER}@${SERVER_IP}:${PROJECT_DIR_ON_SERVER}/
    ssh ${SERVER_USER}@${SERVER_IP} "cd ${PROJECT_DIR_ON_SERVER} && docker compose down && docker compose up -d --build && sleep 5 && docker compose ps"
    
    echo -e "${GREEN}✅ Deployment complete!${NC}"
}

# Main logic
if check_ssh_key; then
    deploy_ssh_key
elif command -v expect &> /dev/null; then
    deploy_with_expect
elif command -v sshpass &> /dev/null; then
    deploy_with_sshpass
else
    echo -e "${YELLOW}No automatic password tool found. Using manual entry.${NC}"
    echo -e "${BLUE}Tip: Install 'expect' or 'sshpass' for automatic password handling:${NC}"
    echo -e "${BLUE}  macOS: brew install expect${NC}"
    echo -e "${BLUE}  Or set up SSH keys: ssh-copy-id ${SERVER_USER}@${SERVER_IP}${NC}"
    echo ""
    deploy_manual
fi

echo ""
echo -e "${GREEN}=== Deployment Summary ===${NC}"
echo -e "Server: ${SERVER_USER}@${SERVER_IP}"
echo -e "${GREEN}Your code has been deployed!${NC}"
