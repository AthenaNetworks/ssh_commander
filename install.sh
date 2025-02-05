#!/bin/bash

# Determine OS and architecture
OS="unknown"
case "$(uname -s)" in
    Darwin*)    OS="macos";;
    Linux*)     OS="linux";;
    MINGW*|MSYS*) 
        echo "For Windows systems, please use install.ps1 instead"
        exit 1
        ;;
esac

ARCH="$(uname -m)"
case "$ARCH" in
    x86_64)  ARCH="x64";;
    aarch64|arm64) ARCH="arm64";;
esac

# Ensure we're in the right directory
if [ ! -d "ssh-commander" ] && [ -f "ssh-commander-${OS}-${ARCH}.tar.gz" ]; then
    tar xzf "ssh-commander-${OS}-${ARCH}.tar.gz"
fi

if [ ! -d "ssh-commander" ]; then
    echo "Error: ssh-commander directory not found. Please ensure you're in the directory where you extracted the archive."
    exit 1
fi

cd ssh-commander

# Find the right executable
EXECUTABLE="ssh-commander-${OS}-${ARCH}"

if [ ! -f "$EXECUTABLE" ]; then
    echo "Error: No compatible executable found for your system ($OS-$ARCH)"
    exit 1
fi

# Create installation directories
sudo mkdir -p /usr/local/bin
mkdir -p ~/.config/ssh-commander

# Install executable
sudo cp "$EXECUTABLE" /usr/local/bin/ssh-commander
sudo chmod +x /usr/local/bin/ssh-commander

echo "\nSSH Commander has been installed!\n"
echo "To add a new server, use: ssh-commander add"
echo "To remove a server, use: ssh-commander remove [SERVER]\n"
echo "To view a list of configured servers, use: ssh-commander list\n"
echo "For more information, use: ssh-commander --help\n"
