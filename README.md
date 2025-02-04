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

## Installation

### Option 1: Using Pre-built Binaries

1. Download the latest release for your platform from the [releases page](https://github.com/AthenaNetworks/ssh_commander/releases)
2. Extract the archive
3. Run the installation script:
```bash
./install.sh
```

### Option 2: Building from Source

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

SSH Commander uses a YAML configuration file to store server details. By default, it looks for `servers.yaml` in the current directory, but you can specify a different file using the `--config` option.

### Example Configuration

```yaml
# Key-based authentication
- hostname: web1.example.com
  username: admin
  key_file: ~/.ssh/id_rsa
  port: 22  # Optional, defaults to 22

# Password authentication
- hostname: db1.example.com
  username: dbadmin
  password: your_secure_password
  port: 2222

# Multiple servers with similar configurations
- hostname: app1.example.com
  username: deployer
  key_file: ~/.ssh/deploy_key

- hostname: app2.example.com
  username: deployer
  key_file: ~/.ssh/deploy_key
```

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

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

If you encounter any issues or have questions:
1. Check the [Issues](https://github.com/AthenaNetworks/ssh_commander/issues) page
2. Create a new issue with detailed information about your problem
3. Include your OS version and Python version when reporting bugs
