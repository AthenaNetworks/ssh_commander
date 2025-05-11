# SSH Commander v1.0.33

## Changes in this version
- Fixed "No module named email" error by including the email module in PyInstaller builds
- This resolves an issue where users were unable to run the application due to missing email module

## Installation

1. Download the appropriate archive for your platform:
   - macOS ARM64: `ssh-commander-macos-arm64-v1.0.33.tar.gz`
   - macOS x64: `ssh-commander-macos-x64-v1.0.33.tar.gz`
   - Linux x64: `ssh-commander-linux-x64-v1.0.33.tar.gz`
   - Linux ARM64: `ssh-commander-linux-arm64-v1.0.33.tar.gz`
   - Windows x64: `ssh-commander-windows-x64-v1.0.33.zip`

2. Extract the archive
3. Run the installation script:
   ```bash
   ./install.sh
   ```

## Technical Details
The issue was caused by PyInstaller excluding the email module during the build process. While the main application code doesn't directly import this module, it's required by one of the dependencies. This has been fixed by removing the `--exclude-module email` flag from all build scripts.
