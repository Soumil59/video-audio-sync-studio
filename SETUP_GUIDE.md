# Setup Guide - Video-Audio Sync Studio

Simple step-by-step guide to get the application running.

## 📦 What You Need

1. **Python 3.8+** - [Download here](https://www.python.org/downloads/)
2. **FFmpeg** - Video processing tool
3. **This application** - Download/clone this repository

---

## 🪟 Windows Setup

### Step 1: Install Python
1. Download Python from https://www.python.org/downloads/
2. **Important**: Check "Add Python to PATH" during installation
3. Verify: Open Command Prompt and run `python --version`

### Step 2: Install FFmpeg

**Option A: Using Chocolatey (Easier)**
```cmd
# Install Chocolatey first (if not installed):
# Run PowerShell as Administrator and paste:
Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebRequest('https://community.chocolatey.org/install.ps1')).DownloadString())

# Then install FFmpeg:
choco install ffmpeg
```

**Option B: Manual Installation**
1. Download FFmpeg from: https://www.gyan.dev/ffmpeg/builds/
2. Download "ffmpeg-release-essentials.zip"
3. Extract to `C:\ffmpeg`
4. Add to PATH:
   - Search "Environment Variables" in Windows
   - Click "Environment Variables"
   - Under "System variables", find "Path" and click "Edit"
   - Click "New" and add: `C:\ffmpeg\bin`
   - Click OK on all windows

5. Verify: Open NEW Command Prompt and run `ffmpeg -version`

### Step 3: Setup Application
```cmd
# Navigate to project folder
cd C:\path\to\video-audio-sync-studio

# Create virtual environment
python -m venv venv

# Activate it
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the app
python video_audio_sync_pro.py
```

---

## 🍎 macOS Setup

### Step 1: Install Python
Python might already be installed. Check with:
```bash
python3 --version
```

If not installed, download from https://www.python.org/downloads/

### Step 2: Install FFmpeg
```bash
# Install Homebrew if not installed:
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install FFmpeg:
brew install ffmpeg

# Verify:
ffmpeg -version
```

### Step 3: Setup Application
```bash
# Navigate to project folder
cd /path/to/video-audio-sync-studio

# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the app
python video_audio_sync_pro.py
```

---

## 🐧 Linux Setup (Ubuntu/Debian)

### Step 1: Install Python
```bash
# Update package list
sudo apt update

# Install Python and pip
sudo apt install python3 python3-pip python3-venv

# Verify
python3 --version
```

### Step 2: Install FFmpeg
```bash
sudo apt update
sudo apt install ffmpeg

# Verify
ffmpeg -version
```

### Step 3: Setup Application
```bash
# Navigate to project folder
cd /path/to/video-audio-sync-studio

# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the app
python video_audio_sync_pro.py
```

---

## 🚀 Running the Application

### First Time
```bash
# Windows
cd C:\path\to\video-audio-sync-studio
venv\Scripts\activate
python video_audio_sync_pro.py

# macOS/Linux
cd /path/to/video-audio-sync-studio
source venv/bin/activate
python video_audio_sync_pro.py
```

### Create Launch Shortcut (Optional)

**Windows - Create `launch.bat`:**
```batch
@echo off
cd /d %~dp0
call venv\Scripts\activate
python video_audio_sync_pro.py
pause
```
Double-click `launch.bat` to run the app!

**macOS/Linux - Create `launch.sh`:**
```bash
#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
python video_audio_sync_pro.py
```
Make executable: `chmod +x launch.sh`
Run: `./launch.sh`

---

## ❓ Common Issues

### "Python not found"
- **Windows**: Reinstall Python and check "Add to PATH"
- **macOS/Linux**: Use `python3` instead of `python`

### "ffmpeg not found"
- Verify installation: `ffmpeg -version`
- Windows: Check PATH includes FFmpeg bin folder
- Restart terminal/Command Prompt after installation

### "No module named 'PyQt6'"
- Activate virtual environment first
- Then: `pip install -r requirements.txt`

### "Permission denied"
- **macOS/Linux**: Use `sudo` for system-wide installs
- Or install in virtual environment (recommended)

---

## 🎓 Next Steps

1. **Test with sample files**: Try a short video first
2. **Read README.md**: Full documentation and features
3. **Experiment with settings**: Try different quality presets
4. **Check examples folder**: Sample test cases (if provided)

---

## 💡 Tips

- **Keep virtual environment activated** while using the app
- **Update dependencies**: `pip install -r requirements.txt --upgrade`
- **Check FFmpeg version**: Newer versions have better performance
- **Use SSD if possible**: Faster video encoding

---

Need help? Check README.md or create an issue on GitHub!
