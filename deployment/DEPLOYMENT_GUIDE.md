# FT-Bot Production Deployment Guide

Complete guide for deploying the FT-Bot application to a Linux server with security best practices.

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Initial Server Setup](#initial-server-setup)
3. [Application Deployment](#application-deployment)
4. [SSL/HTTPS Setup](#sslhttps-setup)
5. [Docker Setup for Freqtrade](#docker-setup-for-freqtrade)
6. [Security Hardening](#security-hardening)
7. [Monitoring & Maintenance](#monitoring--maintenance)
8. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Server Requirements
- **OS**: Ubuntu 22.04 LTS or later (or similar Linux distribution)
- **RAM**: Minimum 2GB (4GB+ recommended)
- **Storage**: 20GB+ SSD
- **CPU**: 2+ cores recommended
- **Domain**: A domain name pointing to your server's IP

### Required Software
- Python 3.12+ (default on Ubuntu 24.04)
- Node.js 20+ LTS (or 22+)
- Nginx
- Docker & Docker Compose
- Git
- Certbot (for SSL certificates)

---

## Initial Server Setup

### 1. Update System
```bash
sudo apt update && sudo apt upgrade -y
```

### 2. Install Required Packages
```bash
# Install Python and dependencies (Python 3.12 is default on Ubuntu 24.04)
sudo apt install -y python3.12 python3.12-venv python3-pip

# Install Node.js 20+ LTS (using NodeSource)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Install Nginx
sudo apt install -y nginx

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Install Docker Compose
sudo apt install -y docker-compose-plugin

# Install Certbot for SSL
sudo apt install -y certbot python3-certbot-nginx

# Install Git and other utilities
sudo apt install -y git htop ufw fail2ban
```

### 3. Create Application User
```bash
# Create dedicated user for the application
sudo adduser --system --group --home /opt/ft-bot ftbot

# Add ftbot user to docker group
sudo usermod -aG docker ftbot

# Set up directory structure
sudo mkdir -p /opt/ft-bot/{backend,frontend,workspaces,bt-userdir,deployment}
sudo chown -R ftbot:ftbot /opt/ft-bot
```

### 4. Configure Firewall
```bash
# Enable UFW firewall
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Allow SSH (change port if using non-standard)
sudo ufw allow 22/tcp

# Allow HTTP and HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Enable firewall
sudo ufw enable
```

### 5. Configure Fail2Ban
```bash
# Copy default jail config
sudo cp /etc/fail2ban/jail.conf /etc/fail2ban/jail.local

# Edit and enable SSH and Nginx jails
sudo nano /etc/fail2ban/jail.local

# Restart fail2ban
sudo systemctl restart fail2ban
```

---

## Application Deployment

### 1. Clone Repository
```bash
# Switch to ftbot user
sudo su - ftbot

# Clone the repository
cd /opt/ft-bot
git clone <your-repo-url> .

# Or if already cloned on local machine, use rsync:
# rsync -avz --exclude='.venv' --exclude='node_modules' \
#   --exclude='workspaces' --exclude='bt-userdir' \
#   /path/to/local/ft-bot/ ftbot@your-server:/opt/ft-bot/
```

### 2. Set Up Backend

```bash
# Create Python virtual environment
cd /opt/ft-bot
python3.12 -m venv .venv
source .venv/bin/activate

# Install Python dependencies
pip install --upgrade pip
pip install -r backend/requirements.txt

# Create necessary directories
mkdir -p backend/data workspaces bt-userdir

# Set up environment file
cp deployment/.env.production.template .env.production

# Generate JWT secret
JWT_SECRET=$(openssl rand -hex 32)

# Edit environment file
nano .env.production
# Update FT_JWT_SECRET with the generated value
```

**Important**: Edit `.env.production` and set at minimum:
- `FT_JWT_SECRET` (use the generated value)

### 3. Set Up Frontend

```bash
# Install Node.js dependencies
cd /opt/ft-bot/frontend/tradingg_bot_front
npm ci

# Build production bundle
npm run build

# Verify build output
ls -la dist/
```

### 4. Configure Systemd Service

```bash
# Exit ftbot user
exit

# Copy systemd service file
sudo cp /opt/ft-bot/deployment/systemd/ft-bot-backend.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable service to start on boot
sudo systemctl enable ft-bot-backend

# Start the service
sudo systemctl start ft-bot-backend

# Check status
sudo systemctl status ft-bot-backend

# View logs
sudo journalctl -u ft-bot-backend -f
```

### 5. Configure Nginx

```bash
# Copy Nginx configuration
sudo cp /opt/ft-bot/deployment/nginx/ft-bot.conf /etc/nginx/sites-available/

# Edit configuration - update your domain name
sudo nano /etc/nginx/sites-available/ft-bot.conf
# Replace 'your-domain.com' with your actual domain

# Test Nginx configuration
sudo nginx -t

# Create symlink to enable site
sudo ln -s /etc/nginx/sites-available/ft-bot.conf /etc/nginx/sites-enabled/

# Remove default site
sudo rm /etc/nginx/sites-enabled/default

# Restart Nginx
sudo systemctl restart nginx
```

---

## SSL/HTTPS Setup

### 1. Obtain SSL Certificate with Let's Encrypt

```bash
# Make sure your domain points to your server's IP
# Check with: dig your-domain.com

# Obtain certificate (Nginx plugin method)
sudo certbot --nginx -d your-domain.com -d www.your-domain.com

# Follow the prompts:
# - Enter email for renewal notifications
# - Agree to terms of service
# - Choose whether to redirect HTTP to HTTPS (recommended: yes)

# Verify certificate
sudo certbot certificates

# Test auto-renewal
sudo certbot renew --dry-run
```

### 2. Update Nginx Configuration

The certificate paths in `/etc/nginx/sites-available/ft-bot.conf` should automatically be updated by Certbot. Verify:

```bash
sudo nano /etc/nginx/sites-available/ft-bot.conf

# Ensure these lines point to your certificates:
# ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
# ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

# Test and reload
sudo nginx -t && sudo systemctl reload nginx
```

### 3. Set Up Certificate Auto-Renewal

```bash
# Check certbot timer
sudo systemctl status certbot.timer

# Enable if not already enabled
sudo systemctl enable certbot.timer
```

---

## Docker Setup for Freqtrade

### 1. Prepare Docker Environment

```bash
# Ensure Docker is running
sudo systemctl status docker

# Test Docker installation
docker --version
docker compose version
```

### 2. Set Up Freqtrade Image

```bash
# Pull the official Freqtrade image
docker pull freqtradeorg/freqtrade:stable

# Verify image
docker images | grep freqtrade
```

### 3. Configure User Workspaces

The backend will manage bot containers dynamically. Ensure workspace structure:

```bash
sudo su - ftbot
cd /opt/ft-bot/workspaces

# Example structure for a user:
# workspaces/
#   user1/
#     user/
#       configs/
#         account.json
#         meta.json
#     bots/
#       bot1/
#         user_data/
#           configs/
#             bot.json
#           strategies/
#           data/
```

### 4. Docker Security

```bash
# Enable Docker content trust (optional but recommended)
export DOCKER_CONTENT_TRUST=1

# Limit Docker logging
sudo nano /etc/docker/daemon.json
```

Add:
```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
```

Restart Docker:
```bash
sudo systemctl restart docker
```

---

## Security Hardening

### 1. Secure File Permissions

```bash
# Set proper ownership
sudo chown -R ftbot:ftbot /opt/ft-bot

# Protect environment file
sudo chmod 600 /opt/ft-bot/.env.production

# Protect database
sudo chmod 600 /opt/ft-bot/backend/data/backend.db

# Protect workspace directories
sudo chmod 750 /opt/ft-bot/workspaces
```

### 2. SSH Hardening

```bash
# Edit SSH config
sudo nano /etc/ssh/sshd_config

# Recommended settings:
# Port 2222  # Change default port
# PermitRootLogin no
# PasswordAuthentication no  # Use SSH keys only
# PubkeyAuthentication yes
# X11Forwarding no
# MaxAuthTries 3

# Restart SSH
sudo systemctl restart sshd
```

### 3. System Updates

```bash
# Enable automatic security updates
sudo apt install unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

### 4. Monitoring and Logging

```bash
# Install logrotate configuration for application logs
sudo nano /etc/logrotate.d/ft-bot
```

Add:
```
/var/log/nginx/ft-bot-*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 www-data adm
    sharedscripts
    postrotate
        [ -f /var/run/nginx.pid ] && kill -USR1 `cat /var/run/nginx.pid`
    endscript
}
```

### 5. Backup Strategy

```bash
# Create backup script
sudo nano /opt/ft-bot/backup.sh
```

Add:
```bash
#!/bin/bash
BACKUP_DIR="/opt/ft-bot-backups"
DATE=$(date +%Y%m%d-%H%M%S)
mkdir -p $BACKUP_DIR

# Backup database
cp /opt/ft-bot/backend/data/backend.db $BACKUP_DIR/backend-$DATE.db

# Backup environment config
cp /opt/ft-bot/.env.production $BACKUP_DIR/env-$DATE.backup

# Backup workspaces (configs only, not data)
tar -czf $BACKUP_DIR/workspaces-$DATE.tar.gz -C /opt/ft-bot workspaces --exclude='*/data/*'

# Keep only last 30 days
find $BACKUP_DIR -type f -mtime +30 -delete

echo "Backup completed: $DATE"
```

```bash
# Make executable
sudo chmod +x /opt/ft-bot/backup.sh

# Add to crontab (daily at 2 AM)
sudo crontab -e
# Add: 0 2 * * * /opt/ft-bot/backup.sh >> /var/log/ft-bot-backup.log 2>&1
```

---

## Monitoring & Maintenance

### 1. Service Monitoring

```bash
# Check backend service
sudo systemctl status ft-bot-backend

# View recent logs
sudo journalctl -u ft-bot-backend -n 100

# Follow logs in real-time
sudo journalctl -u ft-bot-backend -f

# Check Nginx
sudo systemctl status nginx
sudo tail -f /var/log/nginx/ft-bot-access.log
sudo tail -f /var/log/nginx/ft-bot-error.log
```

### 2. Health Checks

```bash
# Test backend API
curl -f http://localhost:8000/docs || echo "Backend not responding"

# Test frontend
curl -f https://your-domain.com || echo "Frontend not accessible"

# Check disk space
df -h

# Check memory
free -h

# Check running containers
docker ps
```

### 3. Performance Monitoring

```bash
# Install monitoring tools
sudo apt install -y htop iotop nethogs

# Monitor system resources
htop

# Monitor Docker stats
docker stats

# Monitor Nginx status
curl http://localhost/nginx_status
```

### 4. Log Analysis

```bash
# Check authentication failures
sudo journalctl -u ft-bot-backend | grep -i "failed\|error\|unauthorized"

# Check Nginx errors
sudo tail -100 /var/log/nginx/ft-bot-error.log

# Check system logs
sudo journalctl -p err -n 50
```

---

## Troubleshooting

### Backend Service Won't Start

```bash
# Check detailed logs
sudo journalctl -u ft-bot-backend -n 50 --no-pager

# Check environment file
sudo -u ftbot cat /opt/ft-bot/.env.production

# Test manually
sudo su - ftbot
cd /opt/ft-bot
source .venv/bin/activate
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

### Frontend Not Loading

```bash
# Check Nginx configuration
sudo nginx -t

# Check Nginx logs
sudo tail -50 /var/log/nginx/ft-bot-error.log

# Verify build files exist
ls -la /opt/ft-bot/frontend/tradingg_bot_front/dist/

# Check file permissions
sudo -u www-data ls /opt/ft-bot/frontend/tradingg_bot_front/dist/
```

### SSL Certificate Issues

```bash
# Check certificate status
sudo certbot certificates

# Check certificate expiry
echo | openssl s_client -servername your-domain.com -connect your-domain.com:443 2>/dev/null | openssl x509 -noout -dates

# Renew certificate manually
sudo certbot renew --force-renewal

# Check Nginx SSL configuration
sudo nginx -t
```

### Docker Container Issues

```bash
# List all containers
docker ps -a

# Check container logs
docker logs <container-id>

# Restart Docker
sudo systemctl restart docker

# Clean up stopped containers
docker container prune
```

### Database Issues

```bash
# Check database file
ls -lh /opt/ft-bot/backend/data/backend.db

# Backup and test database
cp /opt/ft-bot/backend/data/backend.db /tmp/backend.db.backup
sqlite3 /opt/ft-bot/backend/data/backend.db "PRAGMA integrity_check;"
```

### High CPU/Memory Usage

```bash
# Check resource usage
htop

# Check backend workers
ps aux | grep uvicorn

# Check Docker containers
docker stats

# Adjust worker count in systemd service
sudo nano /etc/systemd/system/ft-bot-backend.service
# Change --workers parameter
sudo systemctl daemon-reload
sudo systemctl restart ft-bot-backend
```

---

## Updating Production

### Deploying Updates

```bash
# As ftbot user
sudo su - ftbot
cd /opt/ft-bot

# Run deployment script
bash deployment/deploy.sh
```

The script will:
1. Pull latest code from git
2. Update Python dependencies
3. Rebuild frontend
4. Restart backend service
5. Reload Nginx

### Manual Update Process

If you prefer manual updates:

```bash
# 1. Pull latest code
cd /opt/ft-bot
git pull origin main

# 2. Update backend
source .venv/bin/activate
pip install -r backend/requirements.txt

# 3. Update frontend
cd frontend/tradingg_bot_front
npm ci
npm run build

# 4. Restart services
sudo systemctl restart ft-bot-backend
sudo systemctl reload nginx
```

---

## Security Checklist

- [ ] Firewall (UFW) configured and enabled
- [ ] Fail2Ban installed and configured
- [ ] SSH key authentication only (password auth disabled)
- [ ] Non-standard SSH port (optional)
- [ ] SSL/HTTPS enabled with valid certificate
- [ ] JWT_SECRET is strong and unique
- [ ] File permissions properly set (600 for sensitive files)
- [ ] Automatic security updates enabled
- [ ] Backups configured and tested
- [ ] Monitoring and alerting set up
- [ ] Rate limiting enabled in Nginx
- [ ] Security headers configured in Nginx
- [ ] Docker logging limited
- [ ] Database regularly backed up
- [ ] Logs rotated automatically
- [ ] API documentation disabled in production (comment out /docs endpoints)

---

## Support and Resources

- **Project Repository**: [Your GitHub/GitLab URL]
- **Freqtrade Documentation**: https://www.freqtrade.io/
- **FastAPI Documentation**: https://fastapi.tiangolo.com/
- **Nginx Documentation**: https://nginx.org/en/docs/
- **Let's Encrypt**: https://letsencrypt.org/

---

## Quick Reference Commands

```bash
# Service management
sudo systemctl status ft-bot-backend
sudo systemctl restart ft-bot-backend
sudo systemctl stop ft-bot-backend
sudo systemctl start ft-bot-backend

# View logs
sudo journalctl -u ft-bot-backend -f
sudo tail -f /var/log/nginx/ft-bot-access.log

# Nginx
sudo nginx -t
sudo systemctl reload nginx
sudo systemctl restart nginx

# Docker
docker ps
docker logs <container-id>
docker restart <container-id>

# Deployment
cd /opt/ft-bot && bash deployment/deploy.sh

# Backup
/opt/ft-bot/backup.sh

# Check SSL
sudo certbot certificates
sudo certbot renew --dry-run
```
