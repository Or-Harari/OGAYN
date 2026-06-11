#!/bin/bash
# FT-Bot Backup Script
# Backs up database, configurations, and essential data

set -e

# Configuration
BACKUP_DIR="/opt/ft-bot-backups"
DATE=$(date +%Y%m%d-%H%M%S)
RETENTION_DAYS=30

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "======================================"
echo "FT-Bot Backup - $DATE"
echo "======================================"
echo ""

# Create backup directory
mkdir -p $BACKUP_DIR

# Backup database
echo "Backing up database..."
if [ -f "/opt/ft-bot/backend/data/backend.db" ]; then
    cp /opt/ft-bot/backend/data/backend.db $BACKUP_DIR/backend-$DATE.db
    echo -e "${GREEN}✓ Database backed up${NC}"
else
    echo -e "${YELLOW}⚠ Database not found${NC}"
fi

# Backup environment config
echo "Backing up environment configuration..."
if [ -f "/opt/ft-bot/.env.production" ]; then
    cp /opt/ft-bot/.env.production $BACKUP_DIR/env-$DATE.backup
    chmod 600 $BACKUP_DIR/env-$DATE.backup
    echo -e "${GREEN}✓ Environment config backed up${NC}"
else
    echo -e "${YELLOW}⚠ Environment file not found${NC}"
fi

# Backup workspaces (configs only, exclude data directories)
echo "Backing up workspace configurations..."
if [ -d "/opt/ft-bot/workspaces" ]; then
    tar -czf $BACKUP_DIR/workspaces-$DATE.tar.gz \
        -C /opt/ft-bot workspaces \
        --exclude='*/data/*' \
        --exclude='*.pyc' \
        --exclude='__pycache__' 2>/dev/null || true
    echo -e "${GREEN}✓ Workspaces backed up${NC}"
else
    echo -e "${YELLOW}⚠ Workspaces directory not found${NC}"
fi

# Backup Nginx configuration
echo "Backing up Nginx configuration..."
if [ -f "/etc/nginx/sites-available/ft-bot.conf" ]; then
    sudo cp /etc/nginx/sites-available/ft-bot.conf $BACKUP_DIR/nginx-$DATE.conf
    echo -e "${GREEN}✓ Nginx config backed up${NC}"
fi

# Backup systemd service
echo "Backing up systemd service..."
if [ -f "/etc/systemd/system/ft-bot-backend.service" ]; then
    sudo cp /etc/systemd/system/ft-bot-backend.service $BACKUP_DIR/systemd-$DATE.service
    echo -e "${GREEN}✓ Systemd service backed up${NC}"
fi

# Clean up old backups
echo "Cleaning up old backups (older than $RETENTION_DAYS days)..."
find $BACKUP_DIR -type f -mtime +$RETENTION_DAYS -delete
echo -e "${GREEN}✓ Old backups removed${NC}"

# Calculate backup size
BACKUP_SIZE=$(du -sh $BACKUP_DIR | cut -f1)

echo ""
echo "======================================"
echo "Backup complete!"
echo "======================================"
echo "Location: $BACKUP_DIR"
echo "Total size: $BACKUP_SIZE"
echo "Retention: $RETENTION_DAYS days"
echo ""
