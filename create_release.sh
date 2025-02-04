#!/bin/bash

# Check if version is provided
if [ -z "$1" ]; then
    echo "Usage: ./create_release.sh <version>"
    echo "Example: ./create_release.sh v1.0.0"
    exit 1
fi

VERSION=$1

# Ensure we're in the project root
cd "$(dirname "$0")"

# Clean and create release directory
rm -rf release
mkdir -p release

# Run the build script
./build_all.sh

# Create release packages for each platform
cd release

# Create archives for each platform
if [ -f "ssh-commander-macos-arm64" ]; then
    tar -czf "ssh-commander-macos-arm64-${VERSION}.tar.gz" ssh-commander-macos-arm64 servers.yaml.example README.md install.sh
fi

if [ -f "ssh-commander-macos-x64" ]; then
    tar -czf "ssh-commander-macos-x64-${VERSION}.tar.gz" ssh-commander-macos-x64 servers.yaml.example README.md install.sh
fi

if [ -f "ssh-commander-linux-x64" ]; then
    tar -czf "ssh-commander-linux-x64-${VERSION}.tar.gz" ssh-commander-linux-x64 servers.yaml.example README.md install.sh
fi

if [ -f "ssh-commander-linux-arm64" ]; then
    tar -czf "ssh-commander-linux-arm64-${VERSION}.tar.gz" ssh-commander-linux-arm64 servers.yaml.example README.md install.sh
fi

if [ -f "ssh-commander-windows-x64.exe" ]; then
    zip "ssh-commander-windows-x64-${VERSION}.zip" ssh-commander-windows-x64.exe servers.yaml.example README.md install.sh
fi

# Create release notes template
cat > release_notes.md << EOL
# SSH Commander ${VERSION}

## Changes in this version
- [Add your changes here]

## Installation

1. Download the appropriate archive for your platform:
   - macOS ARM64: \`ssh-commander-macos-arm64-${VERSION}.tar.gz\`
   - macOS x64: \`ssh-commander-macos-x64-${VERSION}.tar.gz\`
   - Linux x64: \`ssh-commander-linux-x64-${VERSION}.tar.gz\`
   - Linux ARM64: \`ssh-commander-linux-arm64-${VERSION}.tar.gz\`
   - Windows x64: \`ssh-commander-windows-x64-${VERSION}.zip\`

2. Extract the archive
3. Run the installation script:
   \`\`\`bash
   ./install.sh
   \`\`\`

## Checksums
\`\`\`
$(sha256sum *)
\`\`\`
EOL

echo "Release packages created in the release directory"
echo "Release notes template created at release/release_notes.md"
echo "Next steps:"
echo "1. Edit release_notes.md to add your changes"
echo "2. Create a new release on GitHub:"
echo "   gh release create ${VERSION} --notes-file release_notes.md ./release/*.tar.gz ./release/*.zip"
