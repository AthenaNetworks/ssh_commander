#!/bin/bash
source venv/bin/activate

# Clean previous builds
rm -rf build dist

# Create executable with PyInstaller
pyinstaller --onefile --name ssh-commander ssh_commander.py

echo "Build complete! Your executable is in the dist/ directory"
