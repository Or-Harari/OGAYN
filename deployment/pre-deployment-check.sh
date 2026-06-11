#!/bin/bash
# Pre-Deployment Checklist Script
# Run this script before deploying to production to verify configuration

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}======================================"
echo "FT-Bot Pre-Deployment Checklist"
echo "======================================${NC}"
echo ""

WARNINGS=0
ERRORS=0

# Function to check a condition
check() {
    local name="$1"
    local command="$2"
    local fix="$3"
    
    echo -n "Checking $name... "
    if eval "$command" > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC}"
        return 0
    else
        echo -e "${RED}✗${NC}"
        if [ -n "$fix" ]; then
            echo "  Fix: $fix"
        fi
        ERRORS=$((ERRORS + 1))
        return 1
    fi
}

check_warning() {
    local name="$1"
    local command="$2"
    local recommendation="$3"
    
    echo -n "Checking $name... "
    if eval "$command" > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC}"
        return 0
    else
        echo -e "${YELLOW}⚠${NC}"
        if [ -n "$recommendation" ]; then
            echo "  Recommendation: $recommendation"
        fi
        WARNINGS=$((WARNINGS + 1))
        return 1
    fi
}

echo -e "${BLUE}=== Server Prerequisites ===${NC}"
check "Python 3.12+" "python3.12 --version" "Install Python 3.12: sudo apt install python3.12 python3.12-venv"
check "Node.js 20+" "node --version | grep -E 'v2[0-9]\.|v[3-9][0-9]\.'" "Install Node.js 20+: curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -"
check "Nginx installed" "nginx -v" "Install Nginx: sudo apt install nginx"
check "Docker installed" "docker --version" "Install Docker: curl -fsSL https://get.docker.com -o get-docker.sh && sudo sh get-docker.sh"
check "Git installed" "git --version" "Install Git: sudo apt install git"

echo ""
echo -e "${BLUE}=== User & Permissions ===${NC}"
check "ftbot user exists" "id ftbot" "Create user: sudo adduser --system --group --home /opt/ft-bot ftbot"
check "ftbot in docker group" "groups ftbot | grep docker" "Add to group: sudo usermod -aG docker ftbot"
check "Application directory exists" "[ -d /opt/ft-bot ]" "Create directory: sudo mkdir -p /opt/ft-bot && sudo chown -R ftbot:ftbot /opt/ft-bot"

echo ""
echo -e "${BLUE}=== Application Files ===${NC}"
check "VERSION file exists" "[ -f /opt/ft-bot/VERSION ]" "Clone repository to /opt/ft-bot"
check "Backend directory exists" "[ -d /opt/ft-bot/backend ]" "Clone repository to /opt/ft-bot"
check "Frontend directory exists" "[ -d /opt/ft-bot/frontend/tradingg_bot_front ]" "Clone repository to /opt/ft-bot"
check "Requirements file exists" "[ -f /opt/ft-bot/backend/requirements.txt ]" "Clone repository to /opt/ft-bot"

echo ""
echo -e "${BLUE}=== Environment Configuration ===${NC}"
check "Environment file exists" "[ -f /opt/ft-bot/.env.production ]" "Create from template: cp /opt/ft-bot/deployment/.env.production.template /opt/ft-bot/.env.production"
if [ -f /opt/ft-bot/.env.production ]; then
    check "JWT secret is set" "grep -v 'CHANGE_ME' /opt/ft-bot/.env.production | grep -q 'FT_JWT_SECRET='" "Generate: openssl rand -hex 32, then update .env.production"
    check "Environment file permissions" "[ \$(stat -c '%a' /opt/ft-bot/.env.production) = '600' ]" "Fix permissions: chmod 600 /opt/ft-bot/.env.production"
fi

echo ""
echo -e "${BLUE}=== Python Environment ===${NC}"
check "Virtual environment exists" "[ -d /opt/ft-bot/.venv ]" "Create: python3.12 -m venv /opt/ft-bot/.venv"
if [ -d /opt/ft-bot/.venv ]; then
    check "Dependencies installed" "[ -f /opt/ft-bot/.venv/bin/uvicorn ]" "Install: source .venv/bin/activate && pip install -r backend/requirements.txt"
fi

echo ""
echo -e "${BLUE}=== Frontend Build ===${NC}"
check "Node modules directory exists" "[ -d /opt/ft-bot/frontend/tradingg_bot_front/node_modules ]" "Install: cd frontend/tradingg_bot_front && npm ci"
check "Production build exists" "[ -d /opt/ft-bot/frontend/tradingg_bot_front/dist ]" "Build: cd frontend/tradingg_bot_front && npm run build"
check "Frontend index.html exists" "[ -f /opt/ft-bot/frontend/tradingg_bot_front/dist/index.html ]" "Build: cd frontend/tradingg_bot_front && npm run build"

echo ""
echo -e "${BLUE}=== System Services ===${NC}"
check "Systemd service file exists" "[ -f /etc/systemd/system/ft-bot-backend.service ]" "Install: sudo cp deployment/systemd/ft-bot-backend.service /etc/systemd/system/"
if [ -f /etc/systemd/system/ft-bot-backend.service ]; then
    check "Service enabled" "systemctl is-enabled ft-bot-backend" "Enable: sudo systemctl enable ft-bot-backend"
fi
check "Nginx config exists" "[ -f /etc/nginx/sites-available/ft-bot.conf ]" "Install: sudo cp deployment/nginx/ft-bot.conf /etc/nginx/sites-available/"
check "Nginx config enabled" "[ -L /etc/nginx/sites-enabled/ft-bot.conf ]" "Enable: sudo ln -s /etc/nginx/sites-available/ft-bot.conf /etc/nginx/sites-enabled/"
check "Nginx config is valid" "sudo nginx -t" "Fix Nginx configuration errors"

echo ""
echo -e "${BLUE}=== Security Configuration ===${NC}"
check "UFW firewall installed" "ufw --version" "Install: sudo apt install ufw"
check_warning "UFW firewall enabled" "sudo ufw status | grep -q 'Status: active'" "Enable: sudo ufw enable (after allowing SSH!)"
check_warning "Fail2Ban installed" "fail2ban-client --version" "Install: sudo apt install fail2ban"
check_warning "Certbot installed" "certbot --version" "Install: sudo apt install certbot python3-certbot-nginx"

echo ""
echo -e "${BLUE}=== SSL Certificate ===${NC}"
check_warning "SSL certificate exists" "[ -d /etc/letsencrypt/live ] && [ -n \"\$(ls -A /etc/letsencrypt/live 2>/dev/null)\" ]" "Obtain certificate: sudo certbot --nginx -d your-domain.com"

echo ""
echo -e "${BLUE}=== File Permissions ===${NC}"
if [ -f /opt/ft-bot/.env.production ]; then
    check "Environment file is secure (600)" "[ \$(stat -c '%a' /opt/ft-bot/.env.production) = '600' ]" "Fix: chmod 600 /opt/ft-bot/.env.production"
fi
check "Application owned by ftbot" "[ \$(stat -c '%U' /opt/ft-bot) = 'ftbot' ]" "Fix: sudo chown -R ftbot:ftbot /opt/ft-bot"

echo ""
echo -e "${BLUE}=== Directories ===${NC}"
check "Backend data directory exists" "[ -d /opt/ft-bot/backend/data ]" "Create: mkdir -p /opt/ft-bot/backend/data"
check "Workspaces directory exists" "[ -d /opt/ft-bot/workspaces ]" "Create: mkdir -p /opt/ft-bot/workspaces"
check "Backtest directory exists" "[ -d /opt/ft-bot/bt-userdir ]" "Create: mkdir -p /opt/ft-bot/bt-userdir"

echo ""
echo -e "${BLUE}======================================${NC}"
echo -e "Pre-Deployment Check Complete"
echo -e "${BLUE}======================================${NC}"
echo ""

if [ $ERRORS -gt 0 ]; then
    echo -e "${RED}✗ ${ERRORS} error(s) found - must be fixed before deployment${NC}"
fi

if [ $WARNINGS -gt 0 ]; then
    echo -e "${YELLOW}⚠ ${WARNINGS} warning(s) found - recommended to address${NC}"
fi

if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}✓ All checks passed! Ready for deployment.${NC}"
    echo ""
    echo "Next steps:"
    echo "1. Review configuration files"
    echo "2. Update domain name in Nginx config"
    echo "3. Start services: sudo systemctl start ft-bot-backend"
    echo "4. Obtain SSL certificate: sudo certbot --nginx -d your-domain.com"
    echo "5. Run health check: bash deployment/health-check.sh"
elif [ $ERRORS -eq 0 ]; then
    echo -e "${GREEN}✓ No critical errors found!${NC}"
    echo -e "${YELLOW}⚠ Please address warnings before going to production.${NC}"
else
    echo ""
    echo "Please fix the errors above before deploying."
    exit 1
fi

echo ""
