#!/usr/bin/env python3

__version__ = '1.0.30'
__author__ = 'Josh Finlay'
__email__ = 'josh@athenanetworks.com.au'
__description__ = 'SSH Commander'
__url__ = 'https://github.com/AthenaNetworks/ssh_commander'

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
from typing import List, Dict, Union, Optional
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
        self.config_file = self._find_config_file(config_file)
        self.servers = self._load_servers()
        self._active_sessions = []  # Keep track of active SSH sessions
    
    def _find_config_file(self, config_file: str = None) -> str:
        """Find the appropriate config file location following priority order."""
        # Priority 1: --config argument
        if config_file:
            return config_file
        
        # Priority 2: servers.yaml in application directory
        app_config = os.path.join(os.path.dirname(sys.executable), 'servers.yaml')
        if os.path.isfile(app_config):
            return app_config
        
        # Priority 3: Default location in user's home directory
        return os.path.expanduser("~/.config/ssh-commander/servers.yaml")
    
    def _verify_config(self, config: Union[dict, list]) -> None:
        """Verify the config format and required fields."""
        if not isinstance(config, list):
            raise ValueError("Config must be a list of server entries")
        for server in config:
            if not isinstance(server, dict):
                raise ValueError("Each server entry must be a dictionary")
            if 'hostname' not in server:
                raise ValueError("Each server entry must have a hostname")
    
    def _download_from_s3(self, bucket: str, key: str) -> dict:
        """Download config from S3 bucket."""
        boto3 = get_boto3()
        s3 = boto3.client('s3')
        response = s3.get_object(Bucket=bucket, Key=key)
        return yaml.safe_load(response['Body'].read().decode())
    
    def _download_from_git(self, url: str, branch: str = None) -> dict:
        """Download config from Git repository."""
        git = get_git()
        with tempfile.TemporaryDirectory() as temp_dir:
            # Clone repository
            repo = git.Repo.clone_from(url, temp_dir, branch=branch, depth=1)
            
            # Look for config file
            config_paths = [
                'servers.yaml',
                'config/servers.yaml',
                '.ssh-commander/servers.yaml'
            ]
            
            for path in config_paths:
                full_path = os.path.join(temp_dir, path)
                if os.path.exists(full_path):
                    with open(full_path, 'r') as f:
                        return yaml.safe_load(f)
            
            raise FileNotFoundError(f"Could not find servers.yaml in repository. Tried: {', '.join(config_paths)}")
    
    def _download_from_sftp(self, hostname: str, path: str, username: str = None, key_file: str = None) -> dict:
        """Download config from SFTP server."""
        paramiko = get_paramiko()
        transport = paramiko.Transport((hostname, 22))
        
        if key_file:
            key = paramiko.RSAKey.from_private_key_file(os.path.expanduser(key_file))
            transport.connect(username=username, pkey=key)
        else:
            transport.connect(username=username)
        
        sftp = paramiko.SFTPClient.from_transport(transport)
        with tempfile.NamedTemporaryFile() as temp_file:
            sftp.get(path, temp_file.name)
            return yaml.safe_load(temp_file.read().decode())
    
    def sync_config(self, url: str, dry_run: bool = False, verify: bool = False,
                    username: str = None, key_file: str = None, branch: str = None) -> None:
        """Sync config from a URL to the appropriate location.
        
        Args:
            url: URL to download config from (supports http(s), s3://, git://, sftp://, file://)
            dry_run: If True, only show what would happen
            verify: If True, verify the YAML and server entries after download
            username: Username for SFTP authentication
            key_file: SSH key file for SFTP/Git authentication
            branch: Git branch to use (for git:// URLs)
        """
        # Parse URL and validate scheme
        parsed = urllib.parse.urlparse(url)
        if not parsed.scheme:
            url = 'file://' + os.path.abspath(url)
            parsed = urllib.parse.urlparse(url)
        
        # Create backup of existing config if it exists
        backup_path = None
        if os.path.exists(self.config_file):
            backup_path = f"{self.config_file}.{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak"
            if not dry_run:
                shutil.copy2(self.config_file, backup_path)
            print(f"{Fore.BLUE}Created backup: {Style.RESET_ALL}{backup_path}")
        
        # Download and process the new config
        if dry_run:
            print(f"{Fore.YELLOW}Would download from: {Style.RESET_ALL}{url}")
            print(f"{Fore.YELLOW}Would save to: {Style.RESET_ALL}{self.config_file}")
            return
        
        try:
            # Download config based on URL scheme
            if parsed.scheme == 'file':
                src_path = urllib.request.url2pathname(parsed.path)
                if not os.path.exists(src_path):
                    raise FileNotFoundError(f"Local file not found: {src_path}")
                with open(src_path, 'r') as f:
                    new_config = yaml.safe_load(f)
            
            elif parsed.scheme in ['http', 'https']:
                response = requests.get(url)
                response.raise_for_status()
                new_config = yaml.safe_load(response.text)
            
            elif parsed.scheme == 's3':
                new_config = self._download_from_s3(parsed.netloc, parsed.path.lstrip('/'))
            
            elif parsed.scheme == 'git':
                new_config = self._download_from_git(url, branch)
            
            elif parsed.scheme == 'sftp':
                new_config = self._download_from_sftp(
                    hostname=parsed.hostname,
                    path=parsed.path,
                    username=username or parsed.username,
                    key_file=key_file
                )
            
            else:
                raise ValueError(f"Unsupported URL scheme: {parsed.scheme}")
            
            # Verify the config if requested
            if verify:
                self._verify_config(new_config)
            
            # Ensure config directory exists
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            
            # Write the new config
            with open(self.config_file, 'w') as f:
                yaml.dump(new_config, f)
            
            print(f"{Fore.GREEN}Successfully synced config to: {Style.RESET_ALL}{self.config_file}")
            
        except Exception as e:
            print(f"{Fore.RED}Error syncing config: {Style.RESET_ALL}{str(e)}")
            if backup_path and os.path.exists(backup_path):
                print(f"{Fore.YELLOW}Restoring from backup...{Style.RESET_ALL}")
                shutil.copy2(backup_path, self.config_file)
            raise

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
                key_file = os.path.expanduser(server['key_file'])
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

    def run_command_on_all(self, command: str, tags: List[str] = None):
        """Execute a command on servers matching the specified tags.
        
        Args:
            command: The command to execute
            tags: Optional list of tags to filter servers by. If None, runs on all servers.
        """
        if not self.servers:
            print(f"{Fore.YELLOW}No servers configured. Use 'ssh-commander add' to add servers.{Style.RESET_ALL}")
            return
            
        # Filter servers by tags if specified
        target_servers = self.servers
        if tags:
            target_servers = [s for s in self.servers if any(tag in s.get('tags', ['default']) for tag in tags)]
            if not target_servers:
                print(f"{Fore.YELLOW}No servers found with tags: {', '.join(tags)}{Style.RESET_ALL}")
                return
            
        print(f"{Fore.CYAN}Executing command: {Fore.WHITE}{command}{Style.RESET_ALL}")
        try:
            for server in target_servers:
                print(f"\n{Fore.LIGHTBLUE_EX}Executing on {server['hostname']} ({', '.join(server.get('tags', ['default']))}){Style.RESET_ALL}")
                _, error = self.execute_command(server, command, stream_output=True)
                if error:
                    print(error)
        except KeyboardInterrupt:
            print(f"\n{Fore.YELLOW}Command execution interrupted. Cleaning up...{Style.RESET_ALL}")
            raise  # Re-raise to be caught by main()

    def run_commands_from_file(self, command_file: str, tags: List[str] = None):
        """Execute commands from a file on servers matching the specified tags.
        
        For each server, all commands are executed in sequence using a single SSH connection.
        This is more efficient than running each command across all servers.
        
        Args:
            command_file: Path to file containing commands to execute
            tags: Optional list of tags to filter servers by. If None, runs on all servers.
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
            # Filter servers by tags if specified
            target_servers = self.servers
            if tags:
                target_servers = [s for s in self.servers if any(tag in s.get('tags', ['default']) for tag in tags)]
                if not target_servers:
                    print(f"{Fore.YELLOW}No servers found with tags: {', '.join(tags)}{Style.RESET_ALL}")
                    return
                    
            for server in target_servers:
                print(f"\n{Fore.CYAN}=== Executing commands on {server['hostname']} ({', '.join(server.get('tags', ['default']))}) ==={Style.RESET_ALL}")
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
        
        # Handle tags
        tags_input = input("Enter tags (comma-separated, default: 'default'): ").strip()
        if tags_input:
            server['tags'] = [tag.strip() for tag in tags_input.split(',') if tag.strip()]
        if not tags_input or not server['tags']:
            server['tags'] = ['default']
        
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
            tags = server.get('tags', ['default'])
            print(f"   {Fore.LIGHTBLUE_EX}Tags:{Style.RESET_ALL} {', '.join(tags)}")

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
    print(f"\n  {Fore.LIGHTCYAN_EX}# Execute a command on servers with specific tags{Style.RESET_ALL}")
    print(f"  ssh-commander exec -c 'uptime' -t 'prod,web'")
    print(f"\n  {Fore.LIGHTCYAN_EX}# Execute multiple commands from a file{Style.RESET_ALL}")
    print(f"  ssh-commander exec -f commands.txt")
    print(f"\n  {Fore.LIGHTCYAN_EX}# Execute commands from file on specific tags{Style.RESET_ALL}")
    print(f"  ssh-commander exec -f commands.txt -t 'staging'")
    print(f"\n  {Fore.LIGHTCYAN_EX}# Add a new server{Style.RESET_ALL}")
    print(f"  ssh-commander add")
    print(f"\n  {Fore.LIGHTCYAN_EX}# List configured servers{Style.RESET_ALL}")
    print(f"  ssh-commander list")
    print(f"\n  {Fore.LIGHTCYAN_EX}# Remove a server{Style.RESET_ALL}")
    print(f"  ssh-commander remove server1.example.com")
    
    print(f"\n  {Fore.LIGHTCYAN_EX}# Sync config from URL{Style.RESET_ALL}")
    print(f"  ssh-commander sync https://example.com/servers.yaml")
    print(f"  ssh-commander sync s3://my-bucket/servers.yaml")
    print(f"  ssh-commander sync sftp://user@host/path/servers.yaml --key-file ~/.ssh/id_rsa")
    print(f"  ssh-commander sync git://github.com/org/repo --branch main")
    print(f"  ssh-commander sync --dry-run /path/to/servers.yaml")

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
    
    # Sync command parser
    sync_parser = subparsers.add_parser(
        'sync',
        help='Sync config from a URL',
        description='Download and sync config file from a URL (supports http(s), s3://, git://, sftp://, file://)'
    )
    sync_parser.add_argument(
        'url',
        help='URL to download config from (e.g., https://example.com/servers.yaml)'
    )
    sync_parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would happen without making changes'
    )
    sync_parser.add_argument(
        '--verify',
        action='store_true',
        help='Verify YAML format and server entries after download'
    )
    sync_parser.add_argument(
        '--username',
        help='Username for SFTP authentication'
    )
    sync_parser.add_argument(
        '--key-file',
        help='SSH key file for SFTP/Git authentication'
    )
    sync_parser.add_argument(
        '--branch',
        help='Git branch to use (for git:// URLs)'
    )
    
    # Execute command parser
    exec_parser = subparsers.add_parser(
        'exec',
        help='Execute commands on servers with specified tags',
        description='Execute a single command or commands from a file on servers with specified tags'
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
    exec_parser.add_argument(
        '-t', '--tags',
        help='Comma-separated list of tags to filter servers (default: all servers)',
        metavar='TAGS'
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
            # Priority 2: servers.yaml in application directory
            config_file = os.path.join(os.path.dirname(sys.executable), 'servers.yaml')
            if os.path.isfile(config_file):
                commander = SSHCommander(config_file=config_file)
            else:
                # Priority 3: Default location in user's home directory
                commander = SSHCommander()
        
        if args.command == 'exec':
            # Parse tags if provided
            tags = [t.strip() for t in args.tags.split(',')] if args.tags else None
            
            if args.exec_command:  # Check if -c was used
                commander.run_command_on_all(args.exec_command, tags=tags)
            elif args.exec_file:  # Check if -f was used
                if not os.path.exists(args.exec_file):
                    print(f"{Fore.RED}Error: Command file '{args.exec_file}' not found{Style.RESET_ALL}")
                    print(f"\nExample command file format:")
                    print(f"  # Check system uptime\n  uptime\n  # Check disk space\n  df -h")
                    sys.exit(1)
                commander.run_commands_from_file(args.exec_file, tags=tags)
            else:
                print(f"{Fore.RED}Error: No command specified. Use -c 'command' or -f file{Style.RESET_ALL}")
                exec_parser.print_help()
                sys.exit(1)
        
        elif args.command == 'add':
            commander.add_server()
        
        elif args.command == 'list':
            commander.list_servers()
        elif args.command == 'sync':
            commander.sync_config(
                args.url,
                dry_run=args.dry_run,
                verify=args.verify,
                username=args.username,
                key_file=args.key_file,
                branch=args.branch
            )
        
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
