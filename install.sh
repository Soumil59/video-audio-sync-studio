#!/bin/bash
# Installation script for Video-Audio Sync Editor
# Supports macOS and Linux

set -e

echo "======================================"
echo "Video-Audio Sync Editor Installation"
echo "======================================"
echo ""

# Check Python version
echo "Checking Python version..."
python_version=$(python3 --version 2>&1 | awk '{print $2}')
required_version="3.8"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "Error: Python 3.8 or higher is required. Found: $python_version"
    exit 1
fi
echo "✓ Python $python_version detected"
echo ""

# Check FFmpeg
echo "Checking for FFmpeg..."
if ! command -v ffmpeg &> /dev/null; then
    echo "Warning: FFmpeg not found!"
    echo ""
    echo "Please install FFmpeg:"
    echo "  macOS:   brew install ffmpeg"
    echo "  Ubuntu:  sudo apt install ffmpeg"
    echo "  Fedora:  sudo dnf install ffmpeg"
    echo ""
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    ffmpeg_version=$(ffmpeg -version | head -n1)
    echo "✓ FFmpeg detected: $ffmpeg_version"
fi
echo ""

# Create virtual environment
echo "Creating virtual environment..."
if [ -d "venv" ]; then
    echo "Virtual environment already exists. Skipping..."
else
    python3 -m venv venv
    echo "✓ Virtual environment created"
fi
echo ""

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate
echo "✓ Virtual environment activated"
echo ""

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip --quiet
echo "✓ pip upgraded"
echo ""

# Install dependencies
echo "Installing dependencies..."
echo "(This may take a few minutes...)"
pip install -r requirements.txt --quiet

if [ $? -eq 0 ]; then
    echo "✓ All dependencies installed successfully"
else
    echo "Error: Failed to install some dependencies"
    exit 1
fi
echo ""

# Create launch script
echo "Creating launch script..."
cat > launch.sh << 'EOF'
#!/bin/bash
# Launch script for Video-Audio Sync Editor

# Activate virtual environment
source venv/bin/activate

# Run application
python video_audio_sync_app.py
EOF

chmod +x launch.sh
echo "✓ Launch script created"
echo ""

echo "======================================"
echo "Installation Complete!"
echo "======================================"
echo ""
echo "To run the application:"
echo "  ./launch.sh"
echo ""
echo "Or manually:"
echo "  source venv/bin/activate"
echo "  python video_audio_sync_app.py"
echo ""
echo "Enjoy!"
