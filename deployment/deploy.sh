#!/bin/bash
# FT-Bot Production Deployment Script
# Run this script on your Linux server after initial setup

set -e

echo "======================================"
echo "FT-Bot Production Deployment"
echo "======================================"
echo ""

# Configuration
APP_DIR="/opt/ft-bot"
APP_USER="ftbot"
VENV_DIR="$APP_DIR/.venv"
FRONTEND_DIR="$APP_DIR/frontend/tradingg_bot_front"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if running as root
if [ "$EUID" -eq 0 ]; then 
    echo -e "${RED}Error: Do not run this script as root${NC}"
    echo "Run as the ftbot user: sudo -u ftbot bash deploy.sh"
    exit 1
fi

# Check if we're in the right directory
if [ ! -f "$APP_DIR/VERSION" ]; then
    echo -e "${RED}Error: Not in the correct directory${NC}"
    echo "Expected to be in: $APP_DIR"
    exit 1
fi

# Get version
VERSION=$(cat $APP_DIR/VERSION)
echo -e "${GREEN}Deploying version: $VERSION${NC}"
echo ""

# Pull latest code
echo "==> Pulling latest code from git..."
git fetch origin
git pull origin main

# Backend deployment
echo ""
echo "==> Updating backend..."

# Activate virtual environment and update dependencies
source $VENV_DIR/bin/activate
pip install --upgrade pip
pip install -r $APP_DIR/backend/requirements.txt

# Run database migrations if any
echo "==> Checking database..."
python -c "from backend.app.db.database import engine; from backend.app.db import models; models.Base.metadata.create_all(bind=engine); print('Database check complete')"

# Frontend deployment
echo ""
echo "==> Building frontend..."
cd $FRONTEND_DIR

# Install dependencies (use npm ci for production)
npm ci --production=false

# Build production bundle
npm run build

echo ""
echo -e "${GREEN}Build complete!${NC}"
echo "Frontend built to: $FRONTEND_DIR/dist"

# Restart backend service
echo ""
echo "==> Restarting backend service..."
sudo systemctl restart ft-bot-backend

# Wait for service to start
sleep 3

# Check service status
if systemctl is-active --quiet ft-bot-backend; then
    echo -e "${GREEN}✓ Backend service is running${NC}"
else
    echo -e "${RED}✗ Backend service failed to start${NC}"
    echo "Check logs with: sudo journalctl -u ft-bot-backend -n 50"
    exit 1
fi

# Reload nginx
echo ""
echo "==> Reloading nginx..."
sudo nginx -t && sudo systemctl reload nginx

echo ""
echo -e "${GREEN}======================================"
echo "Deployment complete!"
echo "======================================${NC}"
echo ""
echo "Version deployed: $VERSION"
echo ""
echo "Useful commands:"
echo "  View backend logs:  sudo journalctl -u ft-bot-backend -f"
echo "  View nginx logs:    sudo tail -f /var/log/nginx/ft-bot-*.log"
echo "  Check service:      sudo systemctl status ft-bot-backend"
echo "  Restart service:    sudo systemctl restart ft-bot-backend"
echo ""
