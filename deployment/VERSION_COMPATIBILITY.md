# Version Compatibility Notes

## Current Recommended Versions (as of June 2026)

### Operating System
- **Ubuntu 24.04 LTS** (recommended)
- Ubuntu 22.04 LTS (also supported)
- Other Debian-based distributions with similar package versions

### Python
- **Python 3.12** (default on Ubuntu 24.04)
- Python 3.13 (also works)
- ~~Python 3.11~~ (not available on Ubuntu 24.04 Noble)

### Node.js
- **Node.js 20.x LTS** (recommended)
- Node.js 22.x LTS (also works)
- ~~Node.js 18.x~~ (deprecated as of 2026, no longer receives security updates)

### Other Dependencies
- Docker 29.x or later
- Nginx 1.24+
- Certbot 2.x
- Git 2.x

## Installation Commands

### For Ubuntu 24.04

```bash
# System update
sudo apt update && sudo apt upgrade -y

# Python (already included by default)
sudo apt install -y python3.12 python3.12-venv python3-pip

# Node.js 20 LTS
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Other tools
sudo apt install -y nginx git certbot python3-certbot-nginx ufw fail2ban
```

### For Ubuntu 22.04

```bash
# System update
sudo apt update && sudo apt upgrade -y

# Python (add deadsnakes PPA for newer versions if needed)
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt install -y python3.12 python3.12-venv python3-pip

# Node.js 20 LTS
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Other tools
sudo apt install -y nginx git certbot python3-certbot-nginx ufw fail2ban
```

## Python Version Detection

The application will work with Python 3.12 or 3.13. Use whichever is available:

```bash
# Check available Python version
python3 --version

# Or specifically:
python3.12 --version
python3.13 --version

# Use in virtual environment creation
python3.12 -m venv .venv
# or
python3.13 -m venv .venv
```

## Node.js Version Selection

Node.js LTS versions are recommended for production:

```bash
# Node.js 20.x (Active LTS until April 2026)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -

# Node.js 22.x (Active LTS from October 2024 - April 2027)
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
```

## Troubleshooting Package Installation

### Python not found
```bash
# If python3.12 is not available, check what's installed
apt list --installed | grep python3

# Ubuntu 24.04 has python3.12 by default
# Ubuntu 22.04 might need the deadsnakes PPA

# Add PPA for Ubuntu 22.04
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3.12 python3.12-venv
```

### Node.js deprecated warning
```bash
# If you see deprecation warning for Node 18, upgrade to Node 20
sudo apt remove nodejs
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
node --version  # Should show v20.x.x
```

### Docker already installed
```bash
# If Docker is already installed, you can skip the installation
# Just ensure the ftbot user is in the docker group
sudo usermod -aG docker ftbot

# Verify Docker version
docker --version  # Should be 20.x or later
```

## Version Support Timeline

| Component | Version | Support Status | End of Life |
|-----------|---------|---------------|-------------|
| Ubuntu 24.04 LTS | Noble | Active | April 2029 |
| Ubuntu 22.04 LTS | Jammy | Active | April 2027 |
| Python 3.12 | 3.12.x | Active | October 2028 |
| Python 3.13 | 3.13.x | Active | October 2029 |
| Node.js 20 | 20.x LTS | Active | April 2026 |
| Node.js 22 | 22.x LTS | Active | April 2027 |
| Node.js 18 | 18.x LTS | **EOL** | April 2025 |

## Backward Compatibility

### Migrating from older versions

If you have an existing deployment with older versions:

**From Python 3.11 to 3.12:**
```bash
# Create new virtual environment
cd /opt/ft-bot
python3.12 -m venv .venv-new
source .venv-new/bin/activate
pip install -r backend/requirements.txt

# Test the application
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000

# If successful, replace old venv
deactivate
rm -rf .venv
mv .venv-new .venv

# Restart service
sudo systemctl restart ft-bot-backend
```

**From Node.js 18 to 20:**
```bash
# Remove old Node.js
sudo apt remove nodejs

# Install new version
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Rebuild frontend
cd /opt/ft-bot/frontend/tradingg_bot_front
rm -rf node_modules package-lock.json
npm install
npm run build

# Reload Nginx
sudo systemctl reload nginx
```

## Notes

- Always test version upgrades in a non-production environment first
- Keep package managers (apt, pip, npm) up to date
- Check Python package compatibility with `pip check` after upgrades
- Monitor deprecation warnings in logs
- Plan upgrades during maintenance windows

## Future Updates

When new LTS versions become available:

1. Update this file with new version recommendations
2. Test compatibility with the application
3. Update all deployment documentation
4. Update the pre-deployment check script
5. Announce breaking changes to users

---

**Last Updated:** June 2, 2026  
**Compatible Platforms:** Ubuntu 22.04+, Debian 12+, and derivatives
