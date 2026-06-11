# FT-Bot Production Deployment - Quick Start

Minimal steps to get FT-Bot running on a fresh Linux server.

## Prerequisites
- Ubuntu 22.04 LTS or later (24.04 recommended)
- Domain name pointing to server IP
- Root or sudo access

---

## 1. Initial Server Setup (10 minutes)

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install everything needed
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
curl -fsSL https://get.docker.com -o get-docker.sh
sudo apt install -y python3.12 python3.12-venv python3-pip nodejs nginx \
    certbot python3-certbot-nginx git ufw fail2ban
sudo sh get-docker.sh

# Create application user
sudo adduser --system --group --home /opt/ft-bot ftbot
sudo usermod -aG docker ftbot

# Configure firewall
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable
```

---

## 2. Deploy Application (5 minutes)

```bash
# Clone repository
sudo su - ftbot
cd /opt/ft-bot
git clone <your-repo-url> .

# Set up backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt
mkdir -p backend/data workspaces bt-userdir

# Configure environment
cp deployment/.env.production.template .env.production
nano .env.production
# Set FT_JWT_SECRET=$(openssl rand -hex 32)

# Build frontend
cd frontend/tradingg_bot_front
npm ci
npm run build
cd ~
exit
```

---

## 3. Configure Services (5 minutes)

```bash
# Install systemd service
sudo cp /opt/ft-bot/deployment/systemd/ft-bot-backend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ft-bot-backend
sudo systemctl start ft-bot-backend

# Configure Nginx
sudo cp /opt/ft-bot/deployment/nginx/ft-bot.conf /etc/nginx/sites-available/
sudo nano /etc/nginx/sites-available/ft-bot.conf
# Replace 'your-domain.com' with your actual domain

sudo ln -s /etc/nginx/sites-available/ft-bot.conf /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
```

---

## 4. Set Up SSL (2 minutes)

```bash
# Obtain SSL certificate
sudo certbot --nginx -d your-domain.com -d www.your-domain.com

# Follow prompts, choose redirect HTTP to HTTPS
```

---

## 5. Verify Deployment

```bash
# Check backend
sudo systemctl status ft-bot-backend
sudo journalctl -u ft-bot-backend -n 20

# Check Nginx
sudo nginx -t
curl https://your-domain.com

# Check Docker
docker ps
```

---

## 6. Create First User

Access your domain in browser and use the authentication endpoints to create your first user, or use the API directly:

```bash
curl -X POST https://your-domain.com/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "your-secure-password",
    "full_name": "Admin User"
  }'
```

---

## Done!

Your FT-Bot is now running at: **https://your-domain.com**

### Next Steps:
1. Configure user workspaces
2. Add trading strategies
3. Set up bot containers
4. Configure backups (see DEPLOYMENT_GUIDE.md)

### Important Commands:
```bash
# View logs
sudo journalctl -u ft-bot-backend -f

# Restart backend
sudo systemctl restart ft-bot-backend

# Deploy updates
sudo su - ftbot
cd /opt/ft-bot && bash deployment/deploy.sh
```

For detailed information, see [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)
