# SSH Commander

SSH Commander is a powerful, colorful command-line tool for executing commands across multiple SSH servers simultaneously. It supports both password and key-based authentication, custom ports, and can execute both single commands and command files.

## Features

- 🔑 Supports both password and key-based authentication
- 🌈 Colorized output for better readability
- 📁 Execute commands from files
- 🔄 Interactive server management
- 🔒 Secure password handling (never shown in terminal)
- 🚀 Single binary deployment
- ⚙️ YAML-based configuration
- 📊 Real-time output streaming
- ⌨️ Graceful interrupt handling (Ctrl+C support)

## Installation

### Option 1: Debian Package (Ubuntu/Debian)

1. Download the latest .deb package from the [releases page](https://github.com/AthenaNetworks/ssh_commander/releases)
2. Install using dpkg:
```bash
sudo dpkg -i ssh-commander_*.deb
```

### Option 2: Using Pre-built Binaries

1. Download the latest release for your platform from the [releases page](https://github.com/AthenaNetworks/ssh_commander/releases)
2. Extract the archive
3. Run the installation script:
```bash
./install.sh  # For macOS/Linux
.\install.ps1  # For Windows (Run as Administrator)
```

### Option 3: Building from Source

1. Clone the repository:
```bash
git clone https://github.com/AthenaNetworks/ssh_commander.git
cd ssh_commander
```

2. Create a virtual environment and install dependencies:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

3. Build the executable:
```bash
./build_all.sh
```

## Configuration

SSH Commander stores server configurations in `~/.config/ssh-commander/servers.yaml`. This file is automatically created when you add your first server.

### Configuration Format

The configuration file uses YAML format and supports both key-based and password authentication:

```yaml
# Key-based authentication (recommended)
- hostname: web1.example.com
  username: admin
  key_file: ~/.ssh/id_rsa  # Path to your SSH key
  port: 22  # Optional, defaults to 22

# Password authentication
- hostname: db1.example.com
  username: dbadmin
  password: your_secure_password  # Not recommended for production use
  port: 2222
```

### Security Notes

⚠️ **Important Security Warning**:
- **NEVER store SSH passwords in the config file**
  - Passwords are stored in plaintext and are NOT secure
  - Anyone with access to your config file can see the passwords
  - This includes backup systems, cloud sync, etc.

✅ **Recommended Approach**:
- Use key-based authentication instead
  - Generate an SSH key: `ssh-keygen -t ed25519`
  - Copy to server: `ssh-copy-id user@hostname`
  - Use `key_file: ~/.ssh/id_ed25519` in config

### Configuration Security
- Config file is stored in `~/.config/ssh-commander/servers.yaml`
- File permissions are set to user-only read/write (600)
- SSH key paths support `~` expansion to your home directory

## Usage

### Managing Servers

1. Add a new server interactively:
```bash
ssh-commander add
```

2. List configured servers:
```bash
ssh-commander list
```

3. Remove a server:
```bash
ssh-commander remove web1.example.com
```

### Executing Commands

1. Run a single command on all servers:
```bash
ssh-commander exec -c "uptime"
```

2. Run multiple commands from a file:
```bash
ssh-commander exec -f commands.txt
```

Example `commands.txt`:
```bash
uptime
df -h
free -m
who
```

3. Use a different config file:
```bash
ssh-commander --config prod-servers.yaml exec -c "docker ps"
```

### Real-world Examples

1. Check system status across all servers:
```bash
ssh-commander exec -c "systemctl status nginx"
```

2. Deploy updates:
```bash
ssh-commander exec -c "sudo apt update && sudo apt upgrade -y"
```

3. Monitor disk space:
```bash
ssh-commander exec -c "df -h / /var /home"
```

4. Check running Docker containers:
```bash
ssh-commander exec -c "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"
```

5. Execute a maintenance script:
```bash
# maintenance.txt
systemctl status nginx
df -h
free -m
find /var/log -type f -size +100M -exec ls -lh {} \;

# Run maintenance checks
ssh-commander exec -f maintenance.txt
```

## Output Formatting

SSH Commander uses colors to make output more readable:
- 🔵 Server names are highlighted in blue
- 🟢 Successful output is shown in green
- 🔴 Errors are displayed in red
- 🟣 Command execution status in purple

## Security Considerations

1. Password Storage:
   - Passwords in the config file should be treated with care
   - Consider using key-based authentication when possible
   - Use appropriate file permissions for your config file: `chmod 600 servers.yaml`

2. SSH Keys:
   - Key files should have proper permissions: `chmod 600 ~/.ssh/id_rsa`
   - Consider using different keys for different server groups

3. Network Security:
   - Be mindful of firewalls and network policies
   - Use custom ports if needed
   - Consider using jump hosts for isolated networks

## Contributing

1. Fork the repository
2. Create your feature branch: `git checkout -b feature/amazing-feature`
3. Commit your changes: `git commit -m 'Add amazing feature'`
4. Push to the branch: `git push origin feature/amazing-feature`
5. Open a Pull Request

## License

This project is licensed under the GNU General Public License v3.0 (GPL-3.0) - see the [LICENSE](LICENSE) file for details.

Key points of the GPL-3.0 license:
- ✅ You can use this software for commercial purposes
- ✅ You can modify the source code
- ✅ You can distribute your modifications
- ⚠️ You must disclose the source code of your modifications
- ⚠️ You must license your modifications under the GPL-3.0
- ⚠️ You must state the significant changes you made

## Support

If you encounter any issues or have questions:
1. Check the [Issues](https://github.com/AthenaNetworks/ssh_commander/issues) page
2. Create a new issue with detailed information about your problem
3. Include your OS version and Python version when reporting bugs
