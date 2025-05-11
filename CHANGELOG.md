# SSH Commander Changelog

All notable changes to SSH Commander will be documented in this file.

## [1.0.33] - 2025-05-11

### Fixed
- Fixed "No module named email" error by including the email module in PyInstaller builds
- This resolves an issue where users were unable to run the application due to missing email module
- The issue was caused by PyInstaller excluding the email module during the build process
- While the main application code doesn't directly import this module, it's required by one of the dependencies

### Changed
- Updated build scripts to include the email module:
  - Modified build.sh, build_all.sh, debian/rules, and rpm/ssh-commander.spec
  - Updated GitHub Actions workflow to include email module in all platform builds

## [1.0.32] - 2025-02-17

### Added
- Major CI/CD Pipeline Improvements:
  - Implemented hybrid GitHub Actions runner strategy:
    - Self-hosted Debian 12 runner for Linux builds
    - GitHub-hosted runners for macOS and Windows
  - Enhanced cross-platform build matrix:
    - Linux: x64 and arm64 architectures
    - macOS: Universal binary support (x64 and arm64)
    - Windows: x64 architecture

### Fixed
- Fixed inconsistent Debian package filename across build steps
- Fixed explicit Debian package filename in RPM build step
- Updated CI configuration to use macos-13 for x64 builds
- Set ARCHFLAGS before pip install on macOS
- Specified Python architecture for macOS/Windows builds
- Updated changelog and release workflow
- Corrected changelog format with proper date and maintainer lines
- Added --break-system-packages to pip install
- Fixed macOS runner architectures
- Removed stray shell: bash from Windows step
- Used PowerShell for Windows steps
- Fixed runs-on for macOS builds
- Fixed PyInstaller command structure
- Added --break-system-packages for Linux pip
- Restored actions/setup-python for macOS
- Installed python3-pip on Linux
- Removed macOS Python install

## [1.0.30] - 2025-02-16

### Added
- Config sync feature with support for multiple protocols:
  - HTTP/HTTPS with request handling
  - S3 buckets with boto3 integration
  - Git repositories with branch selection
  - SFTP with key-based authentication
  - Local file paths
- Authentication options:
  - Username for SFTP connections
  - SSH key file for SFTP and Git
  - Git branch selection
- Safety features:
  - Automatic config backups with timestamps
  - Dry run mode to preview changes
  - Config verification
  - Backup restoration on error

### Changed
- Improved config file location handling with proper priority order
- Updated post-install message with more features and colorized output
- Added RPM package support for CentOS/RHEL systems
- Added shell completion scripts for bash and zsh

## [1.0.29] - 2025-02-15

*Earlier versions not documented*
