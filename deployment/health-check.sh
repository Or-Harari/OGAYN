#!/bin/bash
# FT-Bot Health Check Script
# Run this script to verify all services are running correctly

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "======================================"
echo "FT-Bot Health Check"
echo "======================================"
echo ""

# Check backend service
echo -n "Backend service status: "
if systemctl is-active --quiet ft-bot-backend; then
    echo -e "${GREEN}✓ Running${NC}"
else
    echo -e "${RED}✗ Not running${NC}"
    echo "  Fix: sudo systemctl start ft-bot-backend"
fi

# Check if backend is responding
echo -n "Backend API responding: "
if curl -sf http://localhost:8000/docs > /dev/null 2>&1; then
    echo -e "${GREEN}✓ OK${NC}"
else
    echo -e "${RED}✗ Not responding${NC}"
    echo "  Fix: Check logs with 'sudo journalctl -u ft-bot-backend -n 50'"
fi

# Check Nginx
echo -n "Nginx status: "
if systemctl is-active --quiet nginx; then
    echo -e "${GREEN}✓ Running${NC}"
else
    echo -e "${RED}✗ Not running${NC}"
    echo "  Fix: sudo systemctl start nginx"
fi

# Check Nginx config
echo -n "Nginx configuration: "
if sudo nginx -t > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Valid${NC}"
else
    echo -e "${RED}✗ Invalid${NC}"
    echo "  Fix: sudo nginx -t"
fi

# Check frontend files
echo -n "Frontend build exists: "
if [ -d "/opt/ft-bot/frontend/tradingg_bot_front/dist" ] && [ -f "/opt/ft-bot/frontend/tradingg_bot_front/dist/index.html" ]; then
    echo -e "${GREEN}✓ OK${NC}"
else
    echo -e "${RED}✗ Missing${NC}"
    echo "  Fix: cd /opt/ft-bot/frontend/tradingg_bot_front && npm run build"
fi

# Check Docker
echo -n "Docker daemon: "
if systemctl is-active --quiet docker; then
    echo -e "${GREEN}✓ Running${NC}"
else
    echo -e "${RED}✗ Not running${NC}"
    echo "  Fix: sudo systemctl start docker"
fi

# Check environment file
echo -n "Environment file: "
if [ -f "/opt/ft-bot/.env.production" ]; then
    if grep -q "CHANGE_ME" /opt/ft-bot/.env.production 2>/dev/null; then
        echo -e "${YELLOW}⚠ Contains placeholder values${NC}"
        echo "  Fix: Edit /opt/ft-bot/.env.production"
    else
        echo -e "${GREEN}✓ Configured${NC}"
    fi
else
    echo -e "${RED}✗ Missing${NC}"
    echo "  Fix: cp /opt/ft-bot/deployment/.env.production.template /opt/ft-bot/.env.production"
fi

# Check database
echo -n "Database file: "
if [ -f "/opt/ft-bot/backend/data/backend.db" ]; then
    echo -e "${GREEN}✓ Exists${NC}"
else
    echo -e "${YELLOW}⚠ Will be created on first run${NC}"
fi

# Check SSL certificate
echo -n "SSL certificate: "
if [ -f "/etc/letsencrypt/live/"*"/fullchain.pem" ]; then
    CERT_FILE=$(ls /etc/letsencrypt/live/*/fullchain.pem 2>/dev/null | head -1)
    EXPIRY=$(openssl x509 -enddate -noout -in "$CERT_FILE" 2>/dev/null | cut -d= -f2)
    echo -e "${GREEN}✓ Valid (expires: $EXPIRY)${NC}"
else
    echo -e "${YELLOW}⚠ Not configured${NC}"
    echo "  Fix: sudo certbot --nginx -d your-domain.com"
fi

# Check disk space
echo -n "Disk space: "
DISK_USAGE=$(df -h /opt/ft-bot | awk 'NR==2 {print $5}' | sed 's/%//')
if [ "$DISK_USAGE" -lt 80 ]; then
    echo -e "${GREEN}✓ ${DISK_USAGE}% used${NC}"
elif [ "$DISK_USAGE" -lt 90 ]; then
    echo -e "${YELLOW}⚠ ${DISK_USAGE}% used${NC}"
else
    echo -e "${RED}✗ ${DISK_USAGE}% used (critical)${NC}"
fi

# Check memory
echo -n "Memory usage: "
MEM_USAGE=$(free | awk 'NR==2 {printf "%.0f", $3/$2 * 100}')
if [ "$MEM_USAGE" -lt 80 ]; then
    echo -e "${GREEN}✓ ${MEM_USAGE}% used${NC}"
elif [ "$MEM_USAGE" -lt 90 ]; then
    echo -e "${YELLOW}⚠ ${MEM_USAGE}% used${NC}"
else
    echo -e "${RED}✗ ${MEM_USAGE}% used (critical)${NC}"
fi

# Check firewall
echo -n "UFW firewall: "
if sudo ufw status | grep -q "Status: active"; then
    echo -e "${GREEN}✓ Active${NC}"
else
    echo -e "${YELLOW}⚠ Inactive${NC}"
    echo "  Fix: sudo ufw enable"
fi

# Check running bot containers
echo -n "Running bot containers: "
BOT_COUNT=$(docker ps --filter "name=ft-bot-" | grep -c "ft-bot-" || echo "0")
echo -e "${GREEN}$BOT_COUNT${NC}"

echo ""
echo "======================================"
echo "Health check complete"
echo "======================================"
