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
sudo mkdir -p /etc/ssh-commander

# Install executable
sudo cp "$EXECUTABLE" /usr/local/bin/ssh-commander
sudo chmod +x /usr/local/bin/ssh-commander

# Copy example config if no config exists
if [ ! -f /etc/ssh-commander/servers.yaml ]; then
    sudo cp servers.yaml.example /etc/ssh-commander/servers.yaml
    sudo chmod 600 /etc/ssh-commander/servers.yaml
    echo "Created example config at /etc/ssh-commander/servers.yaml"
fi

echo "Installation complete!"
echo "1. Edit your server configuration:"
echo "   sudo nano /etc/ssh-commander/servers.yaml"
echo ""
echo "2. Test the installation:"
echo "   ssh-commander --config /etc/ssh-commander/servers.yaml list"
