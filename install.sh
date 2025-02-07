#!/bin/bash

# Define colors
GREEN="\033[0;32m"
BLUE="\033[0;34m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
NC="\033[0m" # No Color

# Determine OS and architecture
OS="unknown"
case "$(uname -s)" in
    Darwin*)    OS="macos";;
    Linux*)     OS="linux";;
    MINGW*|MSYS*) 
        echo -e "${RED}For Windows systems, please use install.ps1 instead${NC}"
        exit 1
        ;;
esac

ARCH="$(uname -m)"
case "$ARCH" in
    x86_64)  ARCH="x64";;
    aarch64|arm64) ARCH="arm64";;
esac

# Check dependencies on Linux
if [ "$OS" = "linux" ]; then
    echo -e "${BLUE}Checking system dependencies...${NC}"
    
    # Detect package manager
    if command -v apt-get >/dev/null 2>&1; then
        PKG_MANAGER="apt"
        echo -e "${BLUE}Detected Debian/Ubuntu system${NC}"
        
        # Check for either modern or older versions
        if ! dpkg -l | grep -qE 'libffi[78]' || ! dpkg -l | grep -qE 'libssl(3|1\.1)'; then
            echo -e "${YELLOW}Required dependencies not found. Please install:${NC}"
            echo -e "${YELLOW}For modern systems (Ubuntu 22.04+):${NC}"
            echo -e "  ${GREEN}sudo apt-get install libffi8 libssl3${NC}"
            echo -e "${YELLOW}For older systems:${NC}"
            echo -e "  ${GREEN}sudo apt-get install libffi7 libssl1.1${NC}"
            echo
        fi
    elif command -v yum >/dev/null 2>&1; then
        PKG_MANAGER="yum"
        echo -e "${BLUE}Detected CentOS/RHEL system${NC}"
        
        # Check for either modern or older versions
        if ! rpm -qa | grep -qE 'libffi-[78]' || ! rpm -qa | grep -qE 'openssl-(3|1\.1)'; then
            echo -e "${YELLOW}Required dependencies not found. Please install:${NC}"
            echo -e "${YELLOW}For modern systems:${NC}"
            echo -e "  ${GREEN}sudo yum install libffi-8 openssl-3${NC}"
            echo -e "${YELLOW}For older systems:${NC}"
            echo -e "  ${GREEN}sudo yum install libffi-7 openssl-1.1${NC}"
            echo
        fi
    else
        echo -e "${YELLOW}Unable to detect package manager. Please ensure you have:${NC}"
        echo -e "- libffi (version 7 or 8)"
        echo -e "- libssl/openssl (version 1.1 or 3)"
        echo
    fi
fi

# Find the right executable
EXECUTABLE="ssh-commander-${OS}-${ARCH}"

# Check if executable exists
if [ ! -f "$EXECUTABLE" ]; then
    # Try to extract if archive exists
    if [ -f "${EXECUTABLE}.tar.gz" ]; then
        tar xzf "${EXECUTABLE}.tar.gz"
    fi
fi

if [ ! -f "$EXECUTABLE" ]; then
    echo -e "${RED}Error: No compatible executable found for your system ($OS-$ARCH)${NC}"
    exit 1
fi

# Create installation directories
sudo mkdir -p /usr/local/bin
mkdir -p ~/.config/ssh-commander

# Install executable
sudo cp "$EXECUTABLE" /usr/local/bin/ssh-commander
sudo chmod +x /usr/local/bin/ssh-commander

echo
echo -e "${GREEN}✓ SSH Commander has been installed!${NC}"
echo
echo -e "${BLUE}Available commands:${NC}"
echo -e "  ${YELLOW}ssh-commander add${NC}             - Add a new server"
echo -e "  ${YELLOW}ssh-commander remove${NC} SERVER  - Remove a server"
echo -e "  ${YELLOW}ssh-commander list${NC}           - View configured servers"
echo -e "  ${YELLOW}ssh-commander --help${NC}         - Show help and examples"
echo
