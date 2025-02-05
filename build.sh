#!/bin/bash
source venv/bin/activate

# Clean previous builds
rm -rf build dist

# Create executable with PyInstaller
pyinstaller --onefile --noupx --name ssh-commander \
    --exclude-module _bootlocale \
    --exclude-module PIL \
    --exclude-module numpy \
    --exclude-module pandas \
    --exclude-module matplotlib \
    --exclude-module tkinter \
    --exclude-module unittest \
    --exclude-module email \
    --exclude-module http \
    --exclude-module html \
    --exclude-module xml \
    --exclude-module pydoc \
    ssh_commander.py

echo "Build complete! Your executable is in the dist/ directory"
