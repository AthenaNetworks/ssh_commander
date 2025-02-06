#!/usr/bin/env python3

__version__ = '1.0.27'

import warnings
import os
import sys
import time
import threading
import select
from cryptography.utils import CryptographyDeprecationWarning

# Filter out cryptography deprecation warnings from paramiko
warnings.filterwarnings(
    'ignore',
    category=CryptographyDeprecationWarning,
    message='.*TripleDES.*'
)

import sys
import os
import argparse
from typing import List, Dict
import yaml
from getpass import getpass
from colorama import init, Fore, Back, Style

# Initialize colorama
init(autoreset=True)

# Global variable to store paramiko module once loaded
_paramiko = None

def get_paramiko():
    """Lazy load paramiko module only when needed"""
    global _paramiko
    if _paramiko is None:
        import paramiko
        _paramiko = paramiko
    return _paramiko

class SSHCommander:
    def __init__(self, config_file: str = None):
        self.config_file = config_file or os.path.expanduser("~/.config/ssh-commander/servers.yaml")
        self.servers = self._load_servers()
        self._active_sessions = []  # Keep track of active SSH sessions
        
    def _ensure_config_dir(self) -> None:
        """Ensure the config directory exists."""
        config_dir = os.path.dirname(self.config_file)
        os.makedirs(config_dir, exist_ok=True)

    def _load_servers(self) -> List[Dict]:
        """Load server configurations from YAML file."""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    data = yaml.safe_load(f)
                    return [] if data is None else data
            except IOError:
                raise
            except yaml.YAMLError:
                raise

        # If we're adding a server, just return empty list
        if len(sys.argv) > 1 and sys.argv[1] == 'add':
            return []

    def _connect_to_server(self, server: Dict) -> tuple:
        """Connect to a server and return the client."""
        paramiko = get_paramiko()
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        try:
            # Connect using either password or key-based authentication
            if 'key_file' in server:
                key_file = server['key_file']
                if not os.path.exists(key_file):
                    raise FileNotFoundError(f"SSH key file not found: {key_file}")
                    
                client.connect(
                    server['hostname'],
                    username=server['username'],
                    key_filename=key_file,
                    port=server.get('port', 22)
                )
            else:
                client.connect(
                    server['hostname'],
                    username=server['username'],
                    password=server['password'],
                    port=server.get('port', 22)
                )
            return client, None
        except Exception as e:
            return None, f"{Fore.RED}Error connecting to {server['hostname']}: {str(e)}{Style.RESET_ALL}"
    
    def _stream_output(self, channel):
        """Stream output from a channel in real-time."""
        while True:
            if channel.exit_status_ready() and not (channel.recv_ready() or channel.recv_stderr_ready()):
                break

            if channel.recv_ready():
                data = channel.recv(4096)
                if data:
                    sys.stdout.write(data.decode(errors='replace'))
                    sys.stdout.flush()

            if channel.recv_stderr_ready():
                data = channel.recv_stderr(4096)
                if data:
                    sys.stderr.write(f"{Fore.RED}{data.decode(errors='replace')}{Style.RESET_ALL}")
                    sys.stderr.flush()

            time.sleep(0.1)
    
    def execute_command(self, server: Dict, command: str, stream_output=True) -> tuple:
        """Execute a single command on a server and optionally stream the output."""
        client, error = self._connect_to_server(server)
        if error:
            return "", error
            
        try:
            # Start command execution
            channel = client.get_transport().open_session()
            channel.get_pty()
            channel.set_combine_stderr(False)  # Keep stderr separate for color output
            channel.exec_command(command)
            
            # Keep track of this session
            current_session = {'client': client, 'channels': [channel]}
            self._active_sessions.append(current_session)
            
            if stream_output:
                # Start output thread
                output_thread = threading.Thread(target=self._stream_output, args=(channel,))
                output_thread.daemon = True
                output_thread.start()
                
                # Wait for command to complete
                while not channel.exit_status_ready():
                    try:
                        time.sleep(0.1)
                    except KeyboardInterrupt:
                        print(f"\n{Fore.YELLOW}Interrupted. Sending Ctrl+C...{Style.RESET_ALL}")
                        channel.send('\x03')
                        break
                
                # Wait for output thread to finish
                output_thread.join()
                
                # Get exit status
                exit_status = channel.recv_exit_status()
                error = f"{Fore.RED}Command exited with status {exit_status}{Style.RESET_ALL}" if exit_status != 0 else ""
                return "", error  # Output already streamed
            else:
                # For non-streaming mode, collect output and return it
                output = channel.makefile('r').read().strip()
                error = channel.makefile_stderr('r').read().strip()
                exit_status = channel.recv_exit_status()
                
                if exit_status != 0 and not error:
                    error = f"Command exited with status {exit_status}"
                
                return output, error
        
        except KeyboardInterrupt:
            print(f"\n{Fore.YELLOW}Interrupted. Closing connection to {server['hostname']}{Style.RESET_ALL}")
            self.cleanup_sessions()
            channel.close()
            os._exit(0)
            
        finally:
            channel.close()

    def cleanup_sessions(self):
        """Clean up all active SSH sessions."""
        for session in self._active_sessions:
            try:
                # Close channels first
                for channel in session['channels']:
                    try:
                        if channel and not channel.closed:
                            channel.close()
                    except Exception as e:
                        print(f"Error closing channel: {e}")
                
                # Then close transport
                client = session['client']
                if client:
                    try:
                        transport = client.get_transport()
                        if transport and transport.active:
                            transport.close()
                        client.close()
                    except Exception as e:
                        print(f"Error closing client: {e}")
            except Exception as e:
                print(f"Error during cleanup: {e}")
        self._active_sessions.clear()

    def run_command_on_all(self, command: str):
        """Execute a command on all servers."""
        if not self.servers:
            print(f"{Fore.YELLOW}No servers configured. Use 'ssh-commander add' to add servers.{Style.RESET_ALL}")
            return
            
        print(f"{Fore.CYAN}Executing command: {Fore.WHITE}{command}{Style.RESET_ALL}")
        try:
            for server in self.servers:
                print(f"\n{Fore.LIGHTBLUE_EX}Executing on {server['hostname']}{Style.RESET_ALL}")
                _, error = self.execute_command(server, command, stream_output=True)
                if error:
                    print(error)
        except KeyboardInterrupt:
            print(f"\n{Fore.YELLOW}Command execution interrupted. Cleaning up...{Style.RESET_ALL}")
            raise  # Re-raise to be caught by main()

    def run_commands_from_file(self, command_file: str):
        """Execute commands from a file on all servers.
        
        For each server, all commands are executed in sequence using a single SSH connection.
        This is more efficient than running each command across all servers.
        """
        if not self.servers:
            print(f"{Fore.YELLOW}No servers configured. Use 'ssh-commander add' to add servers.{Style.RESET_ALL}")
            return
            
        try:
            with open(command_file, 'r') as f:
                commands = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        except FileNotFoundError:
            print(f"{Fore.RED}Error: Command file {command_file} not found{Style.RESET_ALL}")
            return
            
        if not commands:
            print(f"{Fore.YELLOW}Warning: No commands found in {command_file}{Style.RESET_ALL}")
            print("File should contain one command per line. Lines starting with # are ignored.")
            return

        try:
            for server in self.servers:
                print(f"\n{Fore.CYAN}=== Executing commands on {server['hostname']} ==={Style.RESET_ALL}")
                client, error = self._connect_to_server(server)
                
                if error:
                    print(error)
                    continue
                
                cancontinue = True

                try:
                    current_session = {'client': client, 'channels': []}
                    self._active_sessions.append(current_session)
                    
                    for command in commands:
                        if not cancontinue:
                            break

                        print(f"{Fore.YELLOW}>>> {command}{Style.RESET_ALL}", flush=True)
                        
                        # Start command execution
                        channel = client.get_transport().open_session()
                        channel.get_pty()
                        channel.set_combine_stderr(False)  # Keep stderr separate for color output
                        channel.exec_command(command)
                        current_session['channels'].append(channel)
                        
                        # Start output thread
                        output_thread = threading.Thread(target=self._stream_output, args=(channel,))
                        output_thread.daemon = True
                        output_thread.start()
                        
                        # Wait for command to complete
                        while not channel.exit_status_ready():
                            try:
                                time.sleep(0.1)
                            except KeyboardInterrupt:
                                print(f"\n{Fore.YELLOW}Interrupted. Received Ctrl+C...{Style.RESET_ALL}")
                                channel.send('\x03')
                                cancontinue = False
                                break
                        
                        # Wait for output thread to finish
                        output_thread.join()
                        
                        # Check exit status
                        exit_status = channel.recv_exit_status()
                        if exit_status != 0:
                            print(f"\n{Fore.RED}Command exited with status {exit_status}{Style.RESET_ALL}")
                        
                        channel.close()
                except KeyboardInterrupt:
                    print(f"\n{Fore.YELLOW}Interrupted. Closing connection to {server['hostname']}{Style.RESET_ALL}")
                    cancontinue = False
                    break
                            
                except Exception as e:
                    print(f"{Fore.RED}Error connecting to {server['hostname']}: {str(e)}{Style.RESET_ALL}")
                    if current_session:
                        try:
                            current_session['client'].close()
                        except:
                            pass
                        if current_session in self._active_sessions:
                            self._active_sessions.remove(current_session)
                    
        except KeyboardInterrupt:
            print(f"\n{Fore.YELLOW}Cleaning up...{Style.RESET_ALL}")
        finally:
            try:
                self.cleanup_sessions()
                os._exit(0)
            except Exception as e:
                print(f"{Fore.RED}Error during final cleanup: {e}{Style.RESET_ALL}")

    def add_server(self):
        """Add a new server to the configuration."""
        # If no config file exists, initialize an empty one
        if not self.servers:
            print(f"\n{Fore.YELLOW}No config file found. Creating new one at: {self.config_file}{Style.RESET_ALL}")
            self.servers = []
            
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
            print(f"{Fore.LIGHTYELLOW_EX}No servers configured.{Style.RESET_ALL}")
            return
        
        print(f"\n{Fore.LIGHTGREEN_EX}Configured Servers:{Style.RESET_ALL}")
        for i, server in enumerate(self.servers, 1):
            print(f"\n{Fore.LIGHTCYAN_EX}{i}. {server['hostname']}{Style.RESET_ALL}")
            print(f"   {Fore.LIGHTBLUE_EX}Username:{Style.RESET_ALL} {server['username']}")
            auth_type = 'Key' if 'key_file' in server else 'Password'
            auth_color = Fore.LIGHTGREEN_EX if 'key_file' in server else Fore.LIGHTYELLOW_EX
            print(f"   {Fore.LIGHTBLUE_EX}Auth Type:{Style.RESET_ALL} {auth_color}{auth_type}{Style.RESET_ALL}")
            if 'port' in server:
                print(f"   {Fore.LIGHTBLUE_EX}Port:{Style.RESET_ALL} {server['port']}")

    def _save_servers(self):
        """Save the current server configuration to file."""
        self._ensure_config_dir()
        with open(self.config_file, 'w') as f:
            yaml.safe_dump(self.servers, f)

def print_examples():
    """Print usage examples with color formatting"""
    print(f"\n{Fore.LIGHTGREEN_EX}Examples:{Style.RESET_ALL}")
    print(f"  {Fore.LIGHTCYAN_EX}# Execute a command on all servers{Style.RESET_ALL}")
    print(f"  ssh-commander exec -c 'uptime'")
    print(f"\n  {Fore.LIGHTCYAN_EX}# Execute multiple commands from a file{Style.RESET_ALL}")
    print(f"  ssh-commander exec -f commands.txt")
    print(f"\n  {Fore.LIGHTCYAN_EX}# Add a new server{Style.RESET_ALL}")
    print(f"  ssh-commander add")
    print(f"\n  {Fore.LIGHTCYAN_EX}# List configured servers{Style.RESET_ALL}")
    print(f"  ssh-commander list")
    print(f"\n  {Fore.LIGHTCYAN_EX}# Remove a server{Style.RESET_ALL}")
    print(f"  ssh-commander remove server1.example.com")

def main():
    # Create main parser with detailed description
    parser = argparse.ArgumentParser(
        description='SSH Commander - Execute commands on multiple servers via SSH',
        epilog='Use <command> --help for detailed help on each command'
    )
    
    # Global options
    parser.add_argument(
        '--version',
        action='version',
        version=f'ssh-commander {__version__}'
    )
    parser.add_argument(
        '--config',
        help='Path to config file (default: ~/.config/ssh-commander/servers.yaml)',
        metavar='FILE'
    )
    
    # Create subcommand parsers
    subparsers = parser.add_subparsers(
        dest='command',
        title='Available Commands',
        metavar='<command>'
    )
    
    # Execute command parser
    exec_parser = subparsers.add_parser(
        'exec',
        help='Execute commands on all configured servers',
        description='Execute a single command or commands from a file on all configured servers'
    )
    exec_group = exec_parser.add_mutually_exclusive_group(required=True)
    exec_group.add_argument(
        '-c', '--command',
        help='Single command to execute (e.g., "uptime" or "df -h")',
        metavar='CMD',
        dest='exec_command'  # Use a different name to avoid conflict
    )
    exec_group.add_argument(
        '-f', '--file',
        help='File containing commands to execute (one per line)',
        metavar='FILE',
        dest='exec_file'  # Use a different name to avoid conflict
    )
    
    # Add server parser
    add_parser = subparsers.add_parser(
        'add',
        help='Add a new server to the configuration',
        description='Interactive wizard to add a new server configuration'
    )
    
    # List servers parser
    list_parser = subparsers.add_parser(
        'list',
        help='List all configured servers',
        description='Display detailed information about all configured servers'
    )
    
    # Remove server parser
    remove_parser = subparsers.add_parser(
        'remove',
        help='Remove a server from the configuration',
        description='Remove a server by its hostname from the configuration'
    )
    remove_parser.add_argument(
        'hostname',
        help='Hostname of the server to remove (e.g., server1.example.com)'
    )
    
    # Parse arguments
    args = parser.parse_args()
    
    # Show help and examples if no command provided
    if not args.command:
        parser.print_help()
        print_examples()
        sys.exit(1)
    
    try:
        # Priority 1: --config argument if provided
        if args.config:
            if not os.path.isfile(args.config):
                print(f"{Fore.RED}Error: Config file '{args.config}' not found{Style.RESET_ALL}")
                sys.exit(1)
            commander = SSHCommander(config_file=args.config)
        else:
            # Priority 2: servers.yaml in executable directory
            config_file = os.path.join(os.path.dirname(__file__), 'servers.yaml')
            if os.path.isfile(config_file):
                commander = SSHCommander(config_file=config_file)
            else:
                # Priority 3: Default location in user's home directory
                commander = SSHCommander()
        
        if args.command == 'exec':
            if args.exec_command:  # Check if -c was used
                commander.run_command_on_all(args.exec_command)
            elif args.exec_file:  # Check if -f was used
                if not os.path.exists(args.exec_file):
                    print(f"{Fore.RED}Error: Command file '{args.exec_file}' not found{Style.RESET_ALL}")
                    print(f"\nExample command file format:")
                    print(f"  # Check system uptime\n  uptime\n  # Check disk space\n  df -h")
                    sys.exit(1)
                commander.run_commands_from_file(args.exec_file)
            else:
                print(f"{Fore.RED}Error: No command specified. Use -c 'command' or -f file{Style.RESET_ALL}")
                exec_parser.print_help()
                sys.exit(1)
        
        elif args.command == 'add':
            commander.add_server()
        
        elif args.command == 'list':
            commander.list_servers()
        
        elif args.command == 'remove':
            if commander.remove_server(args.hostname):
                print(f"{Fore.GREEN}Server {args.hostname} removed successfully!{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}Error: Server '{args.hostname}' not found in configuration{Style.RESET_ALL}")
                print(f"\nUse '{sys.argv[0]} list' to see configured servers")
    
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Operation cancelled by user{Style.RESET_ALL}")
        sys.exit(130)  # Standard Unix practice: 128 + SIGINT(2)
    
    except Exception as e:
        print(f"{Fore.RED}Error: {str(e)}{Style.RESET_ALL}")
        sys.exit(1)


if __name__ == "__main__":
    main()
