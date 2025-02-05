#!/bin/bash

# Determine the OS
OS="unknown"
case "$(uname -s)" in
    Darwin*)    OS="macos";;
    Linux*)     OS="linux";;
    MINGW*|MSYS*) OS="windows";;
esac

# Determine architecture
ARCH="$(uname -m)"
case "$ARCH" in
    x86_64)  ARCH="x64";;
    aarch64|arm64) ARCH="arm64";;
esac

# Clean previous builds
rm -rf build dist

# Activate virtual environment
source venv/bin/activate

# Install dependencies if needed
pip install -r requirements.txt

# Base executable name
BASE_NAME="ssh-commander"

# Build for current platform
echo "Building for $OS-$ARCH..."
# Common PyInstaller options
PYINSTALLER_OPTS="--onefile --noupx \
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
    --exclude-module pydoc"

if [ "$OS" = "windows" ]; then
    # Windows build
    pyinstaller $PYINSTALLER_OPTS \
        --name "${BASE_NAME}-windows-${ARCH}" \
        --add-binary "venv/Lib/site-packages/bcrypt/_bcrypt.pyd;bcrypt" \
        ssh_commander.py
elif [ "$OS" = "linux" ]; then
    # Linux build
    pyinstaller $PYINSTALLER_OPTS \
        --name "${BASE_NAME}-linux-${ARCH}" \
        ssh_commander.py
else
    # macOS build
    pyinstaller $PYINSTALLER_OPTS \
        --name "${BASE_NAME}-macos-${ARCH}" \
        ssh_commander.py
fi

# Create release directory
mkdir -p release
cp dist/* release/

# Copy additional files
cp servers.yaml release/servers.yaml.example
cp README.md release/ 2>/dev/null || echo "No README.md found"

# Create installation script
cat > release/install.sh << 'EOF'
#!/bin/bash

# Determine OS and architecture
OS="unknown"
case "$(uname -s)" in
    Darwin*)    OS="macos";;
    Linux*)     OS="linux";;
    MINGW*|MSYS*) OS="windows";;
esac

ARCH="$(uname -m)"
case "$ARCH" in
    x86_64)  ARCH="x64";;
    aarch64|arm64) ARCH="arm64";;
esac

# Find the right executable
EXECUTABLE="ssh-commander-${OS}-${ARCH}"
if [ "$OS" = "windows" ]; then
    EXECUTABLE="${EXECUTABLE}.exe"
fi

if [ ! -f "$EXECUTABLE" ]; then
    echo "Error: No compatible executable found for your system ($OS-$ARCH)"
    exit 1
fi

# Create installation directory
sudo mkdir -p /usr/local/bin

# Install executable
sudo cp "$EXECUTABLE" /usr/local/bin/ssh-commander
sudo chmod +x /usr/local/bin/ssh-commander

# Create config directory
mkdir -p ~/.ssh-commander

# Copy example config if no config exists
if [ ! -f ~/.ssh-commander/servers.yaml ]; then
    cp servers.yaml.example ~/.ssh-commander/servers.yaml
    echo "Created example config at ~/.ssh-commander/servers.yaml"
fi

echo "Installation complete! Run 'ssh-commander --help' to get started"
EOF

chmod +x release/install.sh

# Create a README if it doesn't exist
if [ ! -f README.md ]; then
cat > release/README.md << 'EOF'
# SSH Commander

A powerful tool for executing commands on multiple SSH servers.

## Installation

1. Run the installation script:
```bash
./install.sh
```

This will:
- Install the executable to /usr/local/bin
- Create a config directory at ~/.ssh-commander
- Copy the example config file if none exists

## Usage

1. Edit your server configuration:
```bash
nano ~/.ssh-commander/servers.yaml
```

2. List configured servers:
```bash
ssh-commander list
```

3. Execute a command on all servers:
```bash
ssh-commander exec -c "uptime"
```

4. Execute commands from a file:
```bash
ssh-commander exec -f commands.txt
```

## Configuration

The servers.yaml file should contain your server configurations:

```yaml
- hostname: server1.example.com
  username: user1
  key_file: ~/.ssh/id_rsa  # For key-based auth

- hostname: server2.example.com
  username: user2
  password: your_password  # For password-based auth
  port: 2222  # Optional custom port
```
EOF
fi

echo "Build complete! Release files are in the release/ directory"
echo "For each platform, copy all files from the release directory and run install.sh"
