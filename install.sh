#!/usr/bin/env bash
set -e

echo "============================================="
echo " LectureSnapPDF — Installation"
echo "============================================="
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed."
    echo "Install it from https://www.python.org/downloads/ or your package manager."
    exit 1
fi

echo "Step 1: Creating virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
else
    echo "Virtual environment already exists."
fi

echo "Step 2: Installing dependencies..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "Step 3: Downloading fonts..."
python3 -c "from font_manager import FontManager; FontManager().download_fonts()" || \
    echo "Warning: Font download failed. App will use system fonts."

echo ""
echo "============================================="
echo " Installation complete!"
echo ""
echo " To run the app:"
echo "   source venv/bin/activate"
echo "   python3 main.py"
echo "============================================="
