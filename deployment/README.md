# Deployment Files

This directory contains all necessary files and documentation for deploying FT-Bot to production on a Linux server.

## Quick Start

For first-time deployment, follow these in order:

1. **[QUICKSTART.md](QUICKSTART.md)** - Fast deployment in ~20 minutes
2. **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)** - Comprehensive step-by-step guide
3. **[SECURITY_CHECKLIST.md](SECURITY_CHECKLIST.md)** - Security hardening checklist

## Files Overview

### Configuration Files

- **`.env.production.template`** - Environment variables template
  - Copy to `/opt/ft-bot/.env.production` on your server
  - Generate JWT secret: `openssl rand -hex 32`
  
- **`systemd/ft-bot-backend.service`** - Systemd service unit file
  - Install to `/etc/systemd/system/`
  - Manages backend API service lifecycle
  
- **`nginx/ft-bot.conf`** - Nginx server configuration
  - Install to `/etc/nginx/sites-available/`
  - Serves frontend + reverse proxy to backend
  - Includes SSL/HTTPS and security headers

### Scripts

- **`deploy.sh`** - Automated deployment script
  - Pulls latest code
  - Updates dependencies
  - Builds frontend
  - Restarts services
  
- **`backup.sh`** - Backup script
  - Backs up database, configs, and workspaces
  - Automated cleanup (30-day retention)
  - Add to crontab for daily execution
  
- **`health-check.sh`** - Health monitoring script
  - Checks all services
  - Verifies configuration
  - Reports issues with fixes

### Documentation

- **`QUICKSTART.md`** - Fast deployment guide (20 min)
- **`DEPLOYMENT_GUIDE.md`** - Comprehensive deployment documentation
- **`SECURITY_CHECKLIST.md`** - Security hardening checklist
- **`README.md`** - This file

## Deployment Architecture

```
Internet
   │
   ├─→ [Firewall (UFW)]
   │      │
   │      ├─→ Port 80/443 → [Nginx]
   │      │                    │
   │      │                    ├─→ /api/* → [FastAPI Backend :8000]
   │      │                    │              │
   │      │                    │              ├─→ SQLite DB
   │      │                    │              └─→ Workspaces
   │      │                    │
   │      │                    └─→ /* → [React Frontend (static)]
   │      │
   │      └─→ Port 22 → [SSH]
   │
   └─→ [Docker Containers]
          └─→ Freqtrade bots (managed by backend)
```

## File Locations (Production)

```
/opt/ft-bot/
├── .env.production              # Environment variables
├── .venv/                       # Python virtual environment
├── backend/
│   ├── app/                     # FastAPI application
│   └── data/
│       └── backend.db           # SQLite database
├── frontend/
│   └── tradingg_bot_front/
│       └── dist/                # Production build (served by Nginx)
├── workspaces/                  # User workspaces
│   └── user1/
│       ├── user/                # User-level configs
│       └── bots/                # Bot instances
├── bt-userdir/                  # Backtest results
└── deployment/                  # This directory

/etc/systemd/system/
└── ft-bot-backend.service       # Systemd service

/etc/nginx/
├── sites-available/
│   └── ft-bot.conf              # Nginx config
└── sites-enabled/
    └── ft-bot.conf              # Symlink

/etc/letsencrypt/
└── live/your-domain.com/        # SSL certificates

/opt/ft-bot-backups/             # Backup directory
└── [dated backups]
```

## Installation Steps Summary

### 1. Prepare Server
```bash
# Install dependencies
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.12 python3.12-venv nodejs nginx git docker.io

# Create user
sudo adduser --system --group --home /opt/ft-bot ftbot
sudo usermod -aG docker ftbot
```

### 2. Deploy Application
```bash
# Clone and setup
sudo su - ftbot
cd /opt/ft-bot
git clone <repo-url> .

# Backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

# Frontend
cd frontend/tradingg_bot_front
npm ci && npm run build
```

### 3. Configure Services
```bash
# Environment
cp deployment/.env.production.template .env.production
nano .env.production  # Set FT_JWT_SECRET

# Systemd
sudo cp deployment/systemd/ft-bot-backend.service /etc/systemd/system/
sudo systemctl enable --now ft-bot-backend

# Nginx
sudo cp deployment/nginx/ft-bot.conf /etc/nginx/sites-available/
sudo ln -s /etc/nginx/sites-available/ft-bot.conf /etc/nginx/sites-enabled/
sudo systemctl restart nginx
```

### 4. SSL Certificate
```bash
sudo certbot --nginx -d your-domain.com
```

### 5. Verify
```bash
bash deployment/health-check.sh
```

## Common Commands

### Service Management
```bash
# Backend service
sudo systemctl status ft-bot-backend
sudo systemctl restart ft-bot-backend
sudo systemctl stop ft-bot-backend
sudo journalctl -u ft-bot-backend -f

# Nginx
sudo systemctl status nginx
sudo systemctl reload nginx
sudo nginx -t
```

### Deployment
```bash
# Automated deployment
sudo su - ftbot
cd /opt/ft-bot
bash deployment/deploy.sh

# Manual update
git pull origin main
source .venv/bin/activate
pip install -r backend/requirements.txt
cd frontend/tradingg_bot_front && npm ci && npm run build
sudo systemctl restart ft-bot-backend
```

### Monitoring
```bash
# Health check
bash deployment/health-check.sh

# View logs
sudo journalctl -u ft-bot-backend -f
sudo tail -f /var/log/nginx/ft-bot-access.log
sudo tail -f /var/log/nginx/ft-bot-error.log

# Docker containers
docker ps
docker logs <container-id>
```

### Backup & Restore
```bash
# Manual backup
bash deployment/backup.sh

# Automated backup (add to crontab)
crontab -e
# Add: 0 2 * * * /opt/ft-bot/deployment/backup.sh >> /var/log/ft-bot-backup.log 2>&1

# Restore database
cp /opt/ft-bot-backups/backend-<date>.db /opt/ft-bot/backend/data/backend.db
sudo systemctl restart ft-bot-backend
```

## Environment Variables

Required:
- `FT_JWT_SECRET` - JWT signing key (generate with `openssl rand -hex 32`)

Optional:
- `FT_BACKEND_DB` - Database path (default: `backend/data/backend.db`)
- `FT_WS_BASE` - Workspaces directory (default: `workspaces/`)
- `FT_CONTAINER_TZ` - Timezone for containers (default: `Etc/UTC`)
- `FT_BACKTEST_MUTATE_BOT` - Backtest mode (default: `false`)

## Security Considerations

### Critical
1. Set strong `FT_JWT_SECRET` (32+ random characters)
2. Enable HTTPS with valid SSL certificate
3. Configure firewall (UFW) - only ports 22, 80, 443
4. Disable SSH password authentication
5. Set proper file permissions (600 for sensitive files)
6. Enable automatic security updates
7. Configure rate limiting in Nginx
8. Add security headers (already in nginx config)

### Recommended
9. Configure Fail2Ban
10. Set up automated backups
11. Configure monitoring and alerts
12. Use non-standard SSH port (optional)
13. Enable Docker content trust
14. Set up log rotation
15. Regular security audits

See [SECURITY_CHECKLIST.md](SECURITY_CHECKLIST.md) for complete checklist.

## Troubleshooting

### Backend won't start
```bash
# Check logs
sudo journalctl -u ft-bot-backend -n 50

# Test manually
sudo su - ftbot
cd /opt/ft-bot
source .venv/bin/activate
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

### Frontend not loading
```bash
# Check Nginx logs
sudo tail -50 /var/log/nginx/ft-bot-error.log

# Verify build exists
ls -la /opt/ft-bot/frontend/tradingg_bot_front/dist/

# Rebuild frontend
cd /opt/ft-bot/frontend/tradingg_bot_front
npm ci && npm run build
```

### SSL issues
```bash
# Check certificate
sudo certbot certificates

# Renew manually
sudo certbot renew --force-renewal

# Test Nginx config
sudo nginx -t
```

## Support

- **Project Issues**: [GitHub Issues]
- **Freqtrade Docs**: https://www.freqtrade.io/
- **FastAPI Docs**: https://fastapi.tiangolo.com/
- **Nginx Docs**: https://nginx.org/en/docs/

## Maintenance Schedule

### Daily
- Check service status
- Review error logs
- Monitor disk space

### Weekly
- Review access logs
- Check failed login attempts
- Verify backups

### Monthly
- Update system packages
- Test backup restore
- Review user permissions
- Check SSL certificate expiry

### Quarterly
- Security audit
- Update dependencies
- Review and optimize performance
- Disaster recovery drill

---

For detailed instructions, see:
- **Quick Start**: [QUICKSTART.md](QUICKSTART.md)
- **Full Guide**: [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)
- **Security**: [SECURITY_CHECKLIST.md](SECURITY_CHECKLIST.md)
