# Transferring Files to Your Linux Server

This guide explains how to transfer your FT-Bot project from Windows to your Linux server.

## Prerequisites

- Your Linux server is accessible via SSH
- You have sudo access on the server
- Git is installed on both machines (or you'll use alternative transfer method)

## Method 1: Git Repository (Recommended)

This is the cleanest approach for production deployments.

### Step 1: Push to Git Repository

On your Windows machine:

```powershell
# Navigate to project directory
cd C:\Users\orhar\ft-bot

# Add all files to git (if not already done)
git add .
git commit -m "Add production deployment configuration"

# Push to your remote repository (GitHub, GitLab, etc.)
git push origin main
```

### Step 2: Clone on Server

On your Linux server:

```bash
# Create application directory
sudo mkdir -p /opt/ft-bot
sudo chown -R $USER:$USER /opt/ft-bot

# Clone repository
cd /opt/ft-bot
git clone <your-repository-url> .

# Or if already cloned, just pull latest
cd /opt/ft-bot
git pull origin main
```

**Advantages:**
- Version controlled
- Easy updates (`git pull`)
- Excludes unnecessary files automatically
- Professional workflow

---

## Method 2: SCP/SFTP Transfer

If you prefer not to use Git, use SCP to transfer files directly.

### Using SCP (Command Line)

On Windows PowerShell:

```powershell
# Transfer entire project (excluding unnecessary directories)
scp -r C:\Users\orhar\ft-bot\backend your-user@your-server:/tmp/ft-bot-transfer/backend
scp -r C:\Users\orhar\ft-bot\frontend your-user@your-server:/tmp/ft-bot-transfer/frontend
scp -r C:\Users\orhar\ft-bot\deployment your-user@your-server:/tmp/ft-bot-transfer/deployment
scp -r C:\Users\orhar\ft-bot\config your-user@your-server:/tmp/ft-bot-transfer/config
scp -r C:\Users\orhar\ft-bot\scripts your-user@your-server:/tmp/ft-bot-transfer/scripts
scp C:\Users\orhar\ft-bot\README.md your-user@your-server:/tmp/ft-bot-transfer/
scp C:\Users\orhar\ft-bot\VERSION your-user@your-server:/tmp/ft-bot-transfer/
```

On your Linux server:

```bash
# Move to final location
sudo mkdir -p /opt/ft-bot
sudo mv /tmp/ft-bot-transfer/* /opt/ft-bot/
sudo chown -R $USER:$USER /opt/ft-bot
```

### Using WinSCP (GUI)

1. Download and install WinSCP: https://winscp.net/
2. Connect to your server
3. Navigate to `/opt/ft-bot` on server side
4. Navigate to `C:\Users\orhar\ft-bot` on local side
5. Select and transfer these directories/files:
   - `backend/`
   - `frontend/`
   - `deployment/`
   - `config/`
   - `scripts/`
   - `README.md`
   - `VERSION`
6. **Exclude** these directories:
   - `.venv/`
   - `node_modules/`
   - `workspaces/`
   - `bt-userdir/`
   - `.git/` (if not using Git)
   - `__pycache__/`
   - `frontend/tradingg_bot_front/dist/`

---

## Method 3: rsync (Most Efficient)

If you have rsync available (via WSL or Cygwin):

```bash
rsync -avz --exclude='.venv' \
           --exclude='node_modules' \
           --exclude='workspaces' \
           --exclude='bt-userdir' \
           --exclude='__pycache__' \
           --exclude='.git' \
           --exclude='dist' \
           -e ssh \
           /c/Users/orhar/ft-bot/ \
           your-user@your-server:/opt/ft-bot/
```

---

## Files to Exclude from Transfer

**Never transfer these:**
- `.venv/` - Python virtual environment (recreate on server)
- `node_modules/` - Node.js dependencies (reinstall on server)
- `workspaces/` - User data (unless migrating existing data)
- `bt-userdir/` - Backtest results (unless migrating)
- `__pycache__/` - Python cache files
- `frontend/tradingg_bot_front/dist/` - Build output (rebuild on server)
- `.env.production` - Contains secrets (create fresh on server)
- `backend/data/backend.db` - Database (unless migrating)

**Always transfer these:**
- `backend/` - Backend source code
- `frontend/` - Frontend source code
- `deployment/` - Deployment configuration
- `config/` - Configuration files
- `scripts/` - Utility scripts
- `README.md` - Documentation
- `VERSION` - Version file

---

## After Transfer

Once files are on your server:

### 1. Verify File Structure

```bash
cd /opt/ft-bot
ls -la

# You should see:
# backend/
# frontend/
# deployment/
# config/
# scripts/
# README.md
# VERSION
```

### 2. Set Correct Ownership

```bash
# Create ftbot user if not exists
sudo adduser --system --group --home /opt/ft-bot ftbot

# Set ownership
sudo chown -R ftbot:ftbot /opt/ft-bot
```

### 3. Run Pre-Deployment Check

```bash
cd /opt/ft-bot
bash deployment/pre-deployment-check.sh
```

### 4. Set Up Environment

```bash
# Switch to ftbot user
sudo su - ftbot

# Create environment file
cd /opt/ft-bot
cp deployment/.env.production.template .env.production

# Generate JWT secret and update .env.production
echo "FT_JWT_SECRET=$(openssl rand -hex 32)"
nano .env.production
# Paste the JWT secret and ensure ENVIRONMENT=production is set

# Secure the file
chmod 600 .env.production
```

### 5. Install Dependencies

```bash
# Python dependencies
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt

# Frontend dependencies and build
cd frontend/tradingg_bot_front
npm ci
npm run build

# Verify build
ls -la dist/
```

### 6. Follow Deployment Guide

```bash
# Exit ftbot user
exit

# Continue with deployment
cd /opt/ft-bot
# Follow deployment/QUICKSTART.md or deployment/DEPLOYMENT_GUIDE.md
```

---

## Quick Transfer Command

For Git method (recommended):

```powershell
# On Windows
cd C:\Users\orhar\ft-bot
git add .
git commit -m "Production deployment ready"
git push origin main
```

```bash
# On Linux server
sudo mkdir -p /opt/ft-bot
sudo chown $USER:$USER /opt/ft-bot
cd /opt/ft-bot
git clone <your-repo-url> .
bash deployment/pre-deployment-check.sh
```

---

## Troubleshooting Transfer Issues

### SSH Connection Issues
```bash
# Test SSH connection
ssh your-user@your-server

# If using non-standard port
ssh -p 2222 your-user@your-server
```

### Permission Denied
```bash
# On server, ensure you have write access
sudo chown -R $USER:$USER /opt/ft-bot
```

### Large File Transfer Failed
```bash
# Transfer in smaller chunks or use compression
tar -czf ft-bot.tar.gz backend/ frontend/ deployment/ config/ scripts/ README.md VERSION
scp ft-bot.tar.gz your-user@your-server:/tmp/
# On server:
cd /opt/ft-bot
tar -xzf /tmp/ft-bot.tar.gz
```

---

## Security Notes

1. **Never commit `.env.production`** - It contains sensitive secrets
2. **Never commit database files** - Transfer separately if migrating
3. **Use SSH keys** - More secure than password authentication
4. **Verify file permissions** after transfer - Especially for `.env.production` (should be 600)

---

## Next Steps After Transfer

1. ✅ Files transferred to `/opt/ft-bot`
2. ✅ Ownership set to `ftbot:ftbot`
3. ✅ Environment file created and configured
4. ✅ Pre-deployment check passes

**Now proceed with:**
- [QUICKSTART.md](QUICKSTART.md) for fast deployment
- [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) for detailed steps
