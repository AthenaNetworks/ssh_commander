# SSH Commander Changelog

All notable changes to SSH Commander will be documented in this file.

## [1.0.35] - Unreleased

### Changed
- Minor maintenance update; bumped build number.

## [1.0.34] - 2026-04-29

### Fixed
- `sync` command was completely non-functional: missing top-level imports for
  `tempfile`, `urllib.parse`, `urllib.request`, `requests`, `shutil`,
  `datetime`, plus references to undefined `get_boto3()` / `get_git()` lazy
  loaders. All have been added.
- `_load_servers()` returned `None` (instead of `[]`) when the config file did
  not exist for any non-`add` command, causing `TypeError` crashes.
- `execute_command()`'s `finally: channel.close()` could fail with
  `UnboundLocalError` if `open_session()` raised before `channel` was assigned.
- `_save_servers()` and `sync_config()` could call `os.makedirs('')` when a
  caller passed a config path with no directory component.
- `run_commands_from_file()` no longer hard-exits the process via `os._exit(0)`
  on the success path.
- `_download_from_sftp()` now honours the port from `sftp://host:port/...` URLs
  and supports password authentication (via the URL's user info).
- Config files written by `add`, `edit`, `remove` and `sync` are now created
  with `0600` permissions (as the README has always claimed) and written
  atomically via a temp file + rename to avoid corrupting the config on crash.
- Help with no subcommand now exits with status `0` instead of `1`.
- Removed unused / duplicated `import os`, `import sys` and `select` imports.

### Added
- `edit <hostname>` subcommand: change username, key file, password, port,
  tags, or rename a server in place.
- `test` subcommand: parallel SSH connectivity check across servers, with
  optional `--tags` filter.
- `config-path` subcommand: prints the resolved config file path.
- `version` subcommand (alias of `--version` for friendlier UX).
- Non-interactive `add` via flags: `--hostname`, `--username`, `--key-file`,
  `--password`, `--password-stdin`, `--port`, `--tags`, `-y/--yes`.
- `remove` now accepts multiple hostnames at once and prompts for confirmation
  by default (skip with `-y/--yes`).
- `list` gained `--tag`/`-t` filtering and `--output {pretty,hosts,yaml,json}`
  for scripting.
- `exec` gained `-p/--parallel N` for concurrent execution across servers and
  `--stop-on-error` for command files.
- Global flags: `--no-color`, `-q/--quiet`, `-v/--verbose`, `--timeout`,
  `--strict-host-key-checking`.
- Connection timeout is now applied to `connect`, banner and auth steps
  (default 10s) so unreachable hosts no longer block indefinitely.
- `sync` honours `--keep-backups N` to prune old timestamped backups and
  understands `git+https://` / `git+ssh://` URLs.
- Updated bash and zsh completions to include all new subcommands and flags
  and to honour `--config` when discovering hosts and tags.

### Changed
- Exit codes are now meaningful: `0` success, `1` user/config error,
  `2` invalid CLI arguments, `3` one or more servers failed,
  `4` network/DNS error, `130` interrupted.
- `add` rejects duplicate hostnames and validates required fields before
  writing.
- `_connect_to_server` now loads the system known_hosts file and accepts a
  `strict_host_key_checking` flag (defaults to the previous `AutoAddPolicy`
  behaviour for backward compatibility).

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
