# Installing Python on Windows

## Method 1: Official Python Installer (Recommended)

### Download
1. Go to: **https://www.python.org/downloads/**
2. Click **"Download Python 3.11.x"** (or latest 3.11+ version)
3. Save the installer (e.g., `python-3.11.9-amd64.exe`)

### Install
1. **Run the installer**
2. ⚠️ **CRITICAL**: Check **"Add Python to PATH"** at the bottom
3. Click **"Install Now"**
4. Wait for installation to complete
5. Click **"Close"**

### Verify
Open a **new** PowerShell window and run:
```powershell
python --version
```
Should output: `Python 3.11.x` (or similar)

```powershell
pip --version
```
Should output: `pip 23.x.x from ...`

---

## Method 2: Windows Package Manager (winget)

If you have Windows 10/11 with winget:

```powershell
# Install Python 3.11
winget install Python.Python.3.11

# Or install Python 3.12
winget install Python.Python.3.12
```

After installation, **restart PowerShell** and verify:
```powershell
python --version
pip --version
```

---

## Method 3: Chocolatey

If you have Chocolatey installed:

```powershell
# Install Chocolatey first (if needed)
Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))

# Install Python
choco install python --version=3.11.9 -y
```

Restart PowerShell and verify:
```powershell
python --version
pip --version
```

---

## Troubleshooting

### "python is not recognized as an internal or external command"

**Cause**: Python not added to PATH during installation.

**Fix**:
1. Uninstall Python (Settings → Apps → Python)
2. Reinstall and check **"Add Python to PATH"**

OR manually add to PATH:
1. Open **System Properties** → **Environment Variables**
2. Under **System variables**, select **Path** → **Edit**
3. Click **New** and add:
   - `C:\Users\your-user\AppData\Local\Programs\Python\Python311\`
   - `C:\Users\your-user\AppData\Local\Programs\Python\Python311\Scripts\`
4. Click **OK** → restart PowerShell

### Using `py` launcher instead of `python`

If `python` doesn't work but `py` does:

```powershell
# Check Python version
py --version

# Use pip via py
py -m pip install -r requirements.txt

# Create alias in PowerShell profile (optional)
Set-Alias python py
Set-Alias pip "py -m pip"
```

### Multiple Python versions installed

```powershell
# Check all installed versions
py --list

# Use specific version
py -3.11 --version
py -3.11 -m pip install -r requirements.txt
```

---

## After Python is Installed

### Update pip (recommended)
```powershell
python -m pip install --upgrade pip
```

### Install project dependencies
```powershell
cd C:\Users\user\dev\backend
pip install -r requirements.txt
```

### Start the backend
```powershell
uvicorn app.main:app --reload --port 8000
```

---

## Recommended Python Version

**Python 3.11.9** or **Python 3.12.x**

- ✅ Fully compatible with all dependencies
- ✅ Best performance
- ✅ Type hints support (used extensively in this project)

**Avoid**:
- ❌ Python 3.9 or older (missing modern syntax features)
- ❌ Python 3.14+ (too new, dependencies may not have wheels yet)

---

## Quick Installation Summary

```powershell
# 1. Download & install Python from python.org
#    ✅ Check "Add Python to PATH"

# 2. Verify in NEW PowerShell window
python --version
pip --version

# 3. Update pip
python -m pip install --upgrade pip

# 4. Install dependencies
cd C:\Users\user\dev\backend
pip install -r requirements.txt

# 5. Run the backend
uvicorn app.main:app --reload --port 8000
```

**Done!** 🎉
