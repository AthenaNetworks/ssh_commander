#!/usr/bin/env python3

import warnings
from cryptography.utils import CryptographyDeprecationWarning

# Filter out cryptography deprecation warnings from paramiko
warnings.filterwarnings(
    'ignore',
    category=CryptographyDeprecationWarning,
    message='.*TripleDES.*'
)

import paramiko
import sys
import os
import argparse
from typing import List, Dict
import yaml
import os
from getpass import getpass
from colorama import init, Fore, Back, Style

# Initialize colorama
init(autoreset=True)

class SSHCommander:
    def __init__(self, config_file: str = "servers.yaml"):
        self.config_file = config_file
        self.servers = self._load_servers()

    def _get_config_paths(self) -> List[str]:
        """Get list of possible config file paths in order of preference."""
        paths = [
            self.config_file,  # User-specified path or default
            "/etc/ssh-commander/servers.yaml",  # System-wide config
            os.path.expanduser("~/.config/ssh-commander/servers.yaml"),  # User config
            "servers.yaml"  # Local directory
        ]
        return [p for p in paths if p != self.config_file]

    def _load_servers(self) -> List[Dict]:
        """Load server configurations from YAML file."""
        # First try the specified config file
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r') as f:
                return yaml.safe_load(f)

        # Try standard locations
        for config_path in self._get_config_paths():
            if os.path.exists(config_path):
                print(f"Using config file: {config_path}")
                self.config_file = config_path
                with open(config_path, 'r') as f:
                    return yaml.safe_load(f)

        print("Error: No config file found in standard locations:")
        print(f"  - {self.config_file} (specified path)")
        print("  - /etc/ssh-commander/servers.yaml")
        print("  - ~/.config/ssh-commander/servers.yaml")
        print("  - ./servers.yaml")
        sys.exit(1)

    def execute_command(self, server: Dict, command: str) -> tuple:
        """Execute a single command on a server and return the output."""
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        try:
            # Connect using either password or key-based authentication
            if 'key_file' in server:
                client.connect(
                    server['hostname'],
                    username=server['username'],
                    key_filename=server['key_file'],
                    port=server.get('port', 22)
                )
            else:
                client.connect(
                    server['hostname'],
                    username=server['username'],
                    password=server['password'],
                    port=server.get('port', 22)
                )

            stdin, stdout, stderr = client.exec_command(command)
            output = stdout.read().decode().strip()
            error = stderr.read().decode().strip()
            
            return output, error
        
        except Exception as e:
            return "", f"{Fore.RED}Error connecting to {server['hostname']}: {str(e)}{Style.RESET_ALL}"
        
        finally:
            client.close()

    def run_command_on_all(self, command: str):
        """Execute a command on all servers."""
        for server in self.servers:
            print(f"\n{Back.BLUE}{Fore.WHITE} Executing on {server['hostname']} {Style.RESET_ALL}")
            output, error = self.execute_command(server, command)
            
            if output:
                print(f"{Fore.GREEN}Output:{Style.RESET_ALL}")
                print(f"{Fore.CYAN}{output}{Style.RESET_ALL}")
            if error:
                print(f"{Fore.RED}Error:{Style.RESET_ALL}")
                print(f"{Fore.RED}{error}{Style.RESET_ALL}")

    def run_commands_from_file(self, command_file: str):
        """Execute commands from a file on all servers."""
        try:
            with open(command_file, 'r') as f:
                commands = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        except FileNotFoundError:
            print(f"Error: Command file {command_file} not found")
            return

        for command in commands:
            print(f"\n=== Executing command: {command} ===")
            self.run_command_on_all(command)

    def add_server(self):
        """Add a new server to the configuration."""
        print("\nAdding a new server to the configuration")
        server = {}
        server['hostname'] = input("Enter hostname: ").strip()
        server['username'] = input("Enter username: ").strip()
        
        auth_type = input("Authentication type (key/password): ").strip().lower()
        if auth_type == 'key':
            key_file = input("Enter path to SSH key file (default: ~/.ssh/id_rsa): ").strip()
            server['key_file'] = key_file if key_file else '~/.ssh/id_rsa'
        else:
            server['password'] = getpass("Enter password: ")
        
        port = input("Enter SSH port (default: 22): ").strip()
        if port and port.isdigit():
            server['port'] = int(port)
        
        self.servers.append(server)
        self._save_servers()
        print(f"\nServer {server['hostname']} added successfully!")

    def remove_server(self, hostname: str) -> bool:
        """Remove a server from the configuration."""
        initial_length = len(self.servers)
        self.servers = [s for s in self.servers if s['hostname'] != hostname]
        
        if len(self.servers) < initial_length:
            self._save_servers()
            return True
        return False

    def list_servers(self):
        """List all configured servers."""
        if not self.servers:
            print(f"{Fore.YELLOW}No servers configured.{Style.RESET_ALL}")
            return
        
        print(f"\n{Fore.GREEN}Configured Servers:{Style.RESET_ALL}")
        for i, server in enumerate(self.servers, 1):
            print(f"\n{Fore.CYAN}{i}. {Back.CYAN}{Fore.WHITE} {server['hostname']} {Style.RESET_ALL}")
            print(f"   {Fore.BLUE}Username:{Style.RESET_ALL} {server['username']}")
            auth_type = 'Key' if 'key_file' in server else 'Password'
            auth_color = Fore.GREEN if 'key_file' in server else Fore.YELLOW
            print(f"   {Fore.BLUE}Auth Type:{Style.RESET_ALL} {auth_color}{auth_type}{Style.RESET_ALL}")
            if 'port' in server:
                print(f"   {Fore.BLUE}Port:{Style.RESET_ALL} {server['port']}")

    def _save_servers(self):
        """Save the current server configuration to file.
        
        Uses the first available config path from _get_config_paths().
        Creates parent directories if they don't exist.
        """
        config_paths = self._get_config_paths()
        save_path = config_paths[0]  # Use first path (highest priority)
        
        # Create parent directories if they don't exist
        parent_dir = os.path.dirname(save_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
            
        with open(save_path, 'w') as f:
            yaml.safe_dump(self.servers, f)

def main():
    parser = argparse.ArgumentParser(description='Execute commands on multiple servers via SSH')
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Execute command parser
    exec_parser = subparsers.add_parser('exec', help='Execute commands on servers')
    exec_parser.add_argument('-c', '--command', help='Single command to execute')
    exec_parser.add_argument('-f', '--file', help='File containing commands to execute')
    
    # Server management parsers
    subparsers.add_parser('add', help='Add a new server')
    subparsers.add_parser('list', help='List all configured servers')
    remove_parser = subparsers.add_parser('remove', help='Remove a server')
    remove_parser.add_argument('hostname', help='Hostname of the server to remove')
    
    # Global options
    parser.add_argument('--config', default='servers.yaml', help='Server configuration file (default: servers.yaml)')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)

    commander = SSHCommander(args.config)
    
    if args.command == 'exec':
        if not args.command and not args.file:
            exec_parser.print_help()
            sys.exit(1)
        if args.command:
            commander.run_command_on_all(args.command)
        if args.file:
            commander.run_commands_from_file(args.file)
    elif args.command == 'add':
        commander.add_server()
    elif args.command == 'list':
        commander.list_servers()
    elif args.command == 'remove':
        if commander.remove_server(args.hostname):
            print(f"Server {args.hostname} removed successfully!")
        else:
            print(f"Server {args.hostname} not found in configuration.")


if __name__ == "__main__":
    main()
