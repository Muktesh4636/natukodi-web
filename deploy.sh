#!/bin/bash

# One-command deployment script
# Usage: ./deploy.sh

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
LOCAL_DOCKER_COMPOSE_FILE="docker-compose.yml"

echo -e "${BLUE}=== Gundu Ata Deployment Script ===${NC}"
echo ""

# Function to check if SSH key authentication works
check_ssh_auth() {
    ssh -o BatchMode=yes -o ConnectTimeout=5 ${SERVER_USER}@${SERVER_IP} "echo 'SSH key auth works'" 2>/dev/null
}

# Function to deploy using SSH keys (passwordless)
deploy_with_ssh_keys() {
    echo -e "${GREEN}Using SSH key authentication${NC}"
    
    # Step 1: Copy docker-compose.yml
    echo -e "${YELLOW}Step 1/3: Copying docker-compose.yml...${NC}"
    scp -q ${LOCAL_DOCKER_COMPOSE_FILE} ${SERVER_USER}@${SERVER_IP}:${PROJECT_DIR_ON_SERVER}/ || {
        echo -e "${RED}Failed to copy docker-compose.yml${NC}"
        return 1
    }
    
    # Step 2: Copy backend directory (excluding unnecessary files)
    echo -e "${YELLOW}Step 2/3: Copying backend directory...${NC}"
    rsync -avz --progress \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='.pytest_cache' \
        --exclude='venv' \
        --exclude='env' \
        --exclude='.env' \
        --exclude='db.sqlite3' \
        --exclude='*.log' \
        --exclude='staticfiles' \
        --exclude='media' \
        ${LOCAL_BACKEND_DIR}/ ${SERVER_USER}@${SERVER_IP}:${PROJECT_DIR_ON_SERVER}/backend/ || {
        echo -e "${RED}Failed to copy backend directory${NC}"
        return 1
    }
    
    # Step 3: Restart containers
    echo -e "${YELLOW}Step 3/3: Restarting containers on server...${NC}"
    ssh ${SERVER_USER}@${SERVER_IP} << 'ENDSSH'
        cd ~/apk_of_ata
        echo "Stopping containers..."
        docker compose down
        echo "Building and starting containers..."
        docker compose up -d --build
        echo "Waiting for containers to start..."
        sleep 5
        echo "Container status:"
        docker compose ps
        echo ""
        echo "Recent logs:"
        docker compose logs --tail=30 web
ENDSSH
    
    echo -e "${GREEN}✅ Deployment complete!${NC}"
    return 0
}

# Function to deploy with password (interactive)
deploy_with_password() {
    echo -e "${YELLOW}Using password authentication${NC}"
    echo -e "${BLUE}You will be prompted for password: Gunduata@123${NC}"
    echo ""
    
    # Step 1: Copy docker-compose.yml
    echo -e "${YELLOW}Step 1/3: Copying docker-compose.yml...${NC}"
    scp ${LOCAL_DOCKER_COMPOSE_FILE} ${SERVER_USER}@${SERVER_IP}:${PROJECT_DIR_ON_SERVER}/ || {
        echo -e "${RED}Failed to copy docker-compose.yml${NC}"
        return 1
    }
    
    # Step 2: Copy backend directory
    echo -e "${YELLOW}Step 2/3: Copying backend directory...${NC}"
    echo "This may take a minute..."
    scp -r ${LOCAL_BACKEND_DIR} ${SERVER_USER}@${SERVER_IP}:${PROJECT_DIR_ON_SERVER}/ || {
        echo -e "${RED}Failed to copy backend directory${NC}"
        return 1
    }
    
    # Step 3: Restart containers
    echo -e "${YELLOW}Step 3/3: Restarting containers on server...${NC}"
    echo "You will be prompted for password again..."
    ssh ${SERVER_USER}@${SERVER_IP} << 'ENDSSH'
        cd ~/apk_of_ata
        echo "Stopping containers..."
        docker compose down
        echo "Building and starting containers..."
        docker compose up -d --build
        echo "Waiting for containers to start..."
        sleep 5
        echo "Container status:"
        docker compose ps
        echo ""
        echo "Recent logs:"
        docker compose logs --tail=30 web
ENDSSH
    
    echo -e "${GREEN}✅ Deployment complete!${NC}"
    return 0
}

# Main deployment logic
main() {
    # Check if we're in the right directory
    if [ ! -f "docker-compose.yml" ] || [ ! -d "backend" ]; then
        echo -e "${RED}Error: Please run this script from the project root directory${NC}"
        exit 1
    fi
    
    # Check if SSH key authentication works
    if check_ssh_auth; then
        deploy_with_ssh_keys
    else
        echo -e "${YELLOW}SSH key authentication not available. Using password authentication.${NC}"
        echo -e "${BLUE}Tip: Set up SSH keys for passwordless deployment:${NC}"
        echo -e "${BLUE}  ssh-copy-id ${SERVER_USER}@${SERVER_IP}${NC}"
        echo ""
        deploy_with_password
    fi
    
    echo ""
    echo -e "${GREEN}=== Deployment Summary ===${NC}"
    echo -e "Server: ${SERVER_USER}@${SERVER_IP}"
    echo -e "Project: ${PROJECT_DIR_ON_SERVER}"
    echo -e "${GREEN}Your code has been deployed successfully!${NC}"
}

# Run main function
main
