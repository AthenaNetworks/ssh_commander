#!/usr/bin/env python3

__version__ = '1.0.34'
__author__ = 'Josh Finlay'
__email__ = 'josh@athenanetworks.com.au'
__description__ = 'SSH Commander'
__url__ = 'https://github.com/AthenaNetworks/ssh_commander'

import argparse
import os
import shutil
import socket
import stat
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from getpass import getpass
from io import StringIO
from typing import Dict, Iterable, List, Optional, Tuple

import yaml
from colorama import Fore, Style, init as colorama_init
from cryptography.utils import CryptographyDeprecationWarning

# Filter out cryptography deprecation warnings from paramiko before paramiko loads.
warnings.filterwarnings(
    'ignore',
    category=CryptographyDeprecationWarning,
    message='.*TripleDES.*',
)

# Module-level toggles configured from CLI flags. They default to sensible values
# so the library can also be imported and used programmatically.
_QUIET = False
_VERBOSE = False


def _set_output_flags(quiet: bool = False, verbose: bool = False, no_color: bool = False) -> None:
    """Configure colorama and the global quiet/verbose flags."""
    global _QUIET, _VERBOSE
    _QUIET = bool(quiet)
    _VERBOSE = bool(verbose)
    # When --no-color is requested, disable ANSI escapes by stripping them.
    colorama_init(autoreset=True, strip=bool(no_color), convert=None)


def _info(msg: str) -> None:
    if not _QUIET:
        print(msg)


def _verbose(msg: str) -> None:
    if _VERBOSE and not _QUIET:
        print(msg)


# ---------------------------------------------------------------------------
# Lazy module loaders. Heavy or optional modules are imported on first use to
# keep startup snappy and to allow installs without optional features.
# ---------------------------------------------------------------------------

_paramiko = None
_boto3 = None
_git = None
_requests = None


def get_paramiko():
    global _paramiko
    if _paramiko is None:
        import paramiko  # noqa: WPS433 - lazy import is intentional
        _paramiko = paramiko
    return _paramiko


def get_boto3():
    global _boto3
    if _boto3 is None:
        try:
            import boto3  # noqa: WPS433
        except ImportError as exc:  # pragma: no cover - depends on install
            raise ImportError(
                "boto3 is required for s3:// sync URLs. Install with 'pip install boto3'."
            ) from exc
        _boto3 = boto3
    return _boto3


def get_git():
    global _git
    if _git is None:
        try:
            import git  # noqa: WPS433
        except ImportError as exc:  # pragma: no cover - depends on install
            raise ImportError(
                "GitPython is required for git:// sync URLs. Install with 'pip install gitpython'."
            ) from exc
        _git = git
    return _git


def get_requests():
    global _requests
    if _requests is None:
        try:
            import requests  # noqa: WPS433
        except ImportError as exc:  # pragma: no cover - depends on install
            raise ImportError(
                "requests is required for http(s):// sync URLs. Install with 'pip install requests'."
            ) from exc
        _requests = requests
    return _requests


# ---------------------------------------------------------------------------
# Core class
# ---------------------------------------------------------------------------


class SSHCommanderError(Exception):
    """Base error for ssh-commander; raised for user-facing failure conditions."""


class SSHCommander:
    DEFAULT_CONNECT_TIMEOUT = 10  # seconds

    def __init__(self, config_file: Optional[str] = None, connect_timeout: Optional[float] = None):
        self.config_file = self._find_config_file(config_file)
        self.connect_timeout = (
            connect_timeout if connect_timeout is not None else self.DEFAULT_CONNECT_TIMEOUT
        )
        self.servers: List[Dict] = self._load_servers()
        self._active_sessions: List[Dict] = []
        self._sessions_lock = threading.Lock()
        self._output_lock = threading.Lock()

    # -- config discovery / IO -------------------------------------------------

    def _find_config_file(self, config_file: Optional[str] = None) -> str:
        """Find the appropriate config file location following priority order."""
        if config_file:
            return os.path.expanduser(config_file)

        # Use the directory of the running executable when frozen (PyInstaller).
        # In dev mode sys.executable points at the python interpreter which is
        # rarely useful, so we also fall back to the script directory.
        candidate_dirs = []
        if getattr(sys, 'frozen', False):
            candidate_dirs.append(os.path.dirname(sys.executable))
        candidate_dirs.append(os.path.dirname(os.path.abspath(sys.argv[0])))

        for directory in candidate_dirs:
            if not directory:
                continue
            local = os.path.join(directory, 'servers.yaml')
            if os.path.isfile(local):
                return local

        return os.path.expanduser("~/.config/ssh-commander/servers.yaml")

    def _verify_config(self, config) -> None:
        """Verify the config format and required fields."""
        if config is None:
            raise ValueError("Config is empty")
        if not isinstance(config, list):
            raise ValueError("Config must be a list of server entries")
        seen_hosts = set()
        for idx, server in enumerate(config, 1):
            if not isinstance(server, dict):
                raise ValueError(f"Entry #{idx}: each server entry must be a mapping")
            if 'hostname' not in server or not str(server['hostname']).strip():
                raise ValueError(f"Entry #{idx}: missing required 'hostname'")
            if 'username' not in server or not str(server['username']).strip():
                raise ValueError(f"Entry #{idx} ({server['hostname']}): missing required 'username'")
            if 'key_file' not in server and 'password' not in server:
                raise ValueError(
                    f"Entry #{idx} ({server['hostname']}): must have either 'key_file' or 'password'"
                )
            host = str(server['hostname']).strip().lower()
            if host in seen_hosts:
                raise ValueError(f"Duplicate hostname in config: {server['hostname']}")
            seen_hosts.add(host)

    def _load_servers(self) -> List[Dict]:
        """Load server configurations from YAML file."""
        if not os.path.exists(self.config_file):
            return []
        try:
            with open(self.config_file, 'r') as f:
                data = yaml.safe_load(f)
        except (IOError, OSError) as exc:
            raise SSHCommanderError(
                f"Could not read config file {self.config_file}: {exc}"
            ) from exc
        except yaml.YAMLError as exc:
            raise SSHCommanderError(
                f"Invalid YAML in {self.config_file}: {exc}"
            ) from exc
        if data is None:
            return []
        if not isinstance(data, list):
            raise SSHCommanderError(
                f"Invalid config: expected a list of servers, got {type(data).__name__}"
            )
        return data

    def _save_servers(self) -> None:
        """Save the current server configuration with secure permissions."""
        directory = os.path.dirname(self.config_file)
        if directory:
            os.makedirs(directory, exist_ok=True)
        # Write atomically: write to a temp file in the same dir then rename.
        target_dir = directory or '.'
        fd, tmp_path = tempfile.mkstemp(prefix='.servers-', suffix='.yaml', dir=target_dir)
        try:
            with os.fdopen(fd, 'w') as f:
                yaml.safe_dump(self.servers, f, default_flow_style=False, sort_keys=False)
            os.chmod(tmp_path, stat.S_IRUSR | stat.S_IWUSR)  # 0600
            os.replace(tmp_path, self.config_file)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    # -- sync helpers ---------------------------------------------------------

    def _download_from_s3(self, bucket: str, key: str) -> dict:
        """Download config from S3 bucket."""
        boto3 = get_boto3()
        s3 = boto3.client('s3')
        response = s3.get_object(Bucket=bucket, Key=key)
        return yaml.safe_load(response['Body'].read().decode())

    def _download_from_git(self, url: str, branch: Optional[str] = None) -> dict:
        """Download config from Git repository."""
        git = get_git()
        # git:// URLs from argparse are kept verbatim. GitPython accepts the
        # common ssh/https/git transport URLs natively.
        with tempfile.TemporaryDirectory() as temp_dir:
            git.Repo.clone_from(url, temp_dir, branch=branch, depth=1)
            config_paths = [
                'servers.yaml',
                'config/servers.yaml',
                '.ssh-commander/servers.yaml',
            ]
            for path in config_paths:
                full_path = os.path.join(temp_dir, path)
                if os.path.exists(full_path):
                    with open(full_path, 'r') as f:
                        return yaml.safe_load(f)
            raise FileNotFoundError(
                f"Could not find servers.yaml in repository. Tried: {', '.join(config_paths)}"
            )

    def _download_from_sftp(
        self,
        hostname: str,
        path: str,
        username: Optional[str] = None,
        key_file: Optional[str] = None,
        password: Optional[str] = None,
        port: int = 22,
    ) -> dict:
        """Download config from SFTP server."""
        paramiko = get_paramiko()
        transport = paramiko.Transport((hostname, port))
        try:
            if key_file:
                key = paramiko.RSAKey.from_private_key_file(os.path.expanduser(key_file))
                transport.connect(username=username, pkey=key)
            elif password is not None:
                transport.connect(username=username, password=password)
            else:
                transport.connect(username=username)
            sftp = paramiko.SFTPClient.from_transport(transport)
            try:
                with tempfile.NamedTemporaryFile(delete=True) as temp_file:
                    sftp.get(path, temp_file.name)
                    with open(temp_file.name, 'r') as f:
                        return yaml.safe_load(f)
            finally:
                sftp.close()
        finally:
            transport.close()

    def sync_config(
        self,
        url: str,
        dry_run: bool = False,
        verify: bool = False,
        username: Optional[str] = None,
        key_file: Optional[str] = None,
        branch: Optional[str] = None,
        keep_backups: int = 5,
    ) -> None:
        """Sync config from a URL to the configured location.

        Supports http(s)://, s3://, git://, sftp:// and file:// schemes. If the
        URL has no scheme, it's treated as a local file path.
        """
        parsed = urllib.parse.urlparse(url)
        if not parsed.scheme:
            url = 'file://' + urllib.request.pathname2url(os.path.abspath(os.path.expanduser(url)))
            parsed = urllib.parse.urlparse(url)

        if dry_run:
            if os.path.exists(self.config_file):
                _info(
                    f"{Fore.YELLOW}Would back up: {Style.RESET_ALL}{self.config_file}"
                )
            _info(f"{Fore.YELLOW}Would download from: {Style.RESET_ALL}{url}")
            _info(f"{Fore.YELLOW}Would save to: {Style.RESET_ALL}{self.config_file}")
            return

        backup_path: Optional[str] = None
        if os.path.exists(self.config_file):
            backup_path = (
                f"{self.config_file}.{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak"
            )
            shutil.copy2(self.config_file, backup_path)
            try:
                os.chmod(backup_path, stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                pass
            _info(f"{Fore.BLUE}Created backup: {Style.RESET_ALL}{backup_path}")

        try:
            if parsed.scheme == 'file':
                src_path = urllib.request.url2pathname(parsed.path)
                if not os.path.exists(src_path):
                    raise FileNotFoundError(f"Local file not found: {src_path}")
                with open(src_path, 'r') as f:
                    new_config = yaml.safe_load(f)

            elif parsed.scheme in ('http', 'https'):
                requests = get_requests()
                response = requests.get(url, timeout=self.connect_timeout)
                response.raise_for_status()
                new_config = yaml.safe_load(response.text)

            elif parsed.scheme == 's3':
                new_config = self._download_from_s3(parsed.netloc, parsed.path.lstrip('/'))

            elif parsed.scheme in ('git', 'git+https', 'git+ssh'):
                # Strip the git+ prefix if present so GitPython can clone.
                clone_url = url[4:] if url.startswith('git+') else url
                new_config = self._download_from_git(clone_url, branch)

            elif parsed.scheme == 'sftp':
                new_config = self._download_from_sftp(
                    hostname=parsed.hostname,
                    path=parsed.path,
                    username=username or parsed.username,
                    key_file=key_file,
                    password=parsed.password,
                    port=parsed.port or 22,
                )

            else:
                raise ValueError(f"Unsupported URL scheme: {parsed.scheme}")

            if verify:
                self._verify_config(new_config)

            self.servers = new_config if isinstance(new_config, list) else []
            self._save_servers()

            _info(
                f"{Fore.GREEN}Successfully synced config to: "
                f"{Style.RESET_ALL}{self.config_file}"
            )
            self._prune_backups(keep_backups)

        except Exception as exc:
            print(f"{Fore.RED}Error syncing config: {Style.RESET_ALL}{exc}", file=sys.stderr)
            if backup_path and os.path.exists(backup_path):
                _info(f"{Fore.YELLOW}Restoring from backup...{Style.RESET_ALL}")
                shutil.copy2(backup_path, self.config_file)
            raise

    def _prune_backups(self, keep: int) -> None:
        """Keep at most `keep` most-recent backup files alongside the config."""
        if keep < 0:
            return
        directory = os.path.dirname(self.config_file) or '.'
        prefix = os.path.basename(self.config_file) + '.'
        try:
            entries = [
                os.path.join(directory, name)
                for name in os.listdir(directory)
                if name.startswith(prefix) and name.endswith('.bak')
            ]
        except OSError:
            return
        entries.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        for stale in entries[keep:]:
            try:
                os.unlink(stale)
            except OSError:
                pass

    # -- ssh execution --------------------------------------------------------

    def _build_client(self, strict_host_key_checking: bool = False):
        paramiko = get_paramiko()
        client = paramiko.SSHClient()
        # Always load known_hosts so authentic prior fingerprints take effect.
        try:
            client.load_system_host_keys()
        except (IOError, OSError):
            pass
        if strict_host_key_checking:
            client.set_missing_host_key_policy(paramiko.RejectPolicy())
        else:
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        return client

    def _connect_to_server(
        self,
        server: Dict,
        strict_host_key_checking: bool = False,
    ) -> Tuple[Optional[object], Optional[str]]:
        """Connect to a server and return (client, error_message)."""
        client = self._build_client(strict_host_key_checking=strict_host_key_checking)
        try:
            connect_kwargs = {
                'hostname': server['hostname'],
                'username': server['username'],
                'port': int(server.get('port', 22)),
                'timeout': self.connect_timeout,
                'banner_timeout': self.connect_timeout,
                'auth_timeout': self.connect_timeout,
            }
            if 'key_file' in server:
                key_file = os.path.expanduser(server['key_file'])
                if not os.path.exists(key_file):
                    raise FileNotFoundError(f"SSH key file not found: {key_file}")
                connect_kwargs['key_filename'] = key_file
                connect_kwargs['look_for_keys'] = False
                connect_kwargs['allow_agent'] = False
            else:
                connect_kwargs['password'] = server['password']
                connect_kwargs['look_for_keys'] = False
                connect_kwargs['allow_agent'] = False

            client.connect(**connect_kwargs)
            return client, None
        except Exception as exc:
            try:
                client.close()
            except Exception:
                pass
            return None, (
                f"{Fore.RED}Error connecting to {server['hostname']}: {exc}{Style.RESET_ALL}"
            )

    def _stream_output(self, channel, prefix: str = "", out_buffer=None) -> None:
        """Stream output from a channel until EOF.

        If ``out_buffer`` is provided the data is captured there instead of
        being written to the live terminal, which allows safe parallel
        execution without interleaving.
        """
        try:
            while True:
                if channel.exit_status_ready() and not (
                    channel.recv_ready() or channel.recv_stderr_ready()
                ):
                    break

                wrote = False
                if channel.recv_ready():
                    data = channel.recv(4096)
                    if data:
                        text = data.decode(errors='replace')
                        if out_buffer is not None:
                            out_buffer.write(text)
                        else:
                            with self._output_lock:
                                sys.stdout.write(prefix + text if prefix else text)
                                sys.stdout.flush()
                        wrote = True

                if channel.recv_stderr_ready():
                    data = channel.recv_stderr(4096)
                    if data:
                        text = data.decode(errors='replace')
                        if out_buffer is not None:
                            out_buffer.write(text)
                        else:
                            with self._output_lock:
                                sys.stderr.write(
                                    f"{Fore.RED}{prefix + text if prefix else text}{Style.RESET_ALL}"
                                )
                                sys.stderr.flush()
                        wrote = True

                if not wrote:
                    time.sleep(0.05)
        except Exception:
            # Best-effort streaming: if the channel dies mid-read we just stop.
            return

    def _register_session(self, session: Dict) -> None:
        with self._sessions_lock:
            self._active_sessions.append(session)

    def _unregister_session(self, session: Dict) -> None:
        with self._sessions_lock:
            if session in self._active_sessions:
                self._active_sessions.remove(session)

    def cleanup_sessions(self) -> None:
        """Close all active SSH sessions and channels."""
        with self._sessions_lock:
            sessions = list(self._active_sessions)
            self._active_sessions.clear()
        for session in sessions:
            for channel in session.get('channels', []):
                try:
                    if channel and not channel.closed:
                        channel.close()
                except Exception:
                    pass
            try:
                client = session.get('client')
                if client:
                    transport = client.get_transport()
                    if transport and transport.active:
                        transport.close()
                    client.close()
            except Exception:
                pass

    def _run_one_command(
        self,
        client,
        command: str,
        prefix: str = "",
        out_buffer=None,
    ) -> int:
        """Run a single command on an already-connected client."""
        transport = client.get_transport()
        channel = transport.open_session()
        try:
            channel.get_pty()
            channel.set_combine_stderr(False)
            channel.exec_command(command)

            session = {'client': client, 'channels': [channel]}
            self._register_session(session)
            try:
                output_thread = threading.Thread(
                    target=self._stream_output,
                    args=(channel, prefix, out_buffer),
                )
                output_thread.daemon = True
                output_thread.start()

                while not channel.exit_status_ready():
                    try:
                        time.sleep(0.1)
                    except KeyboardInterrupt:
                        _info(
                            f"\n{Fore.YELLOW}Interrupted. Sending Ctrl+C...{Style.RESET_ALL}"
                        )
                        try:
                            channel.send('\x03')
                        except Exception:
                            pass
                        raise

                output_thread.join()
                return channel.recv_exit_status()
            finally:
                self._unregister_session(session)
        finally:
            try:
                channel.close()
            except Exception:
                pass

    def filter_servers(self, tags: Optional[Iterable[str]] = None) -> List[Dict]:
        """Return the subset of servers matching any of the given tags."""
        if not tags:
            return list(self.servers)
        wanted = {t.strip() for t in tags if t and t.strip()}
        if not wanted:
            return list(self.servers)
        return [
            s for s in self.servers
            if any(tag in s.get('tags', ['default']) for tag in wanted)
        ]

    def run_command_on_all(
        self,
        command: str,
        tags: Optional[List[str]] = None,
        parallel: int = 1,
        strict_host_key_checking: bool = False,
    ) -> int:
        """Execute a command on servers matching the given tags.

        Returns the number of servers that exited with a non-zero status (or
        could not be reached). 0 means every target succeeded.
        """
        if not self.servers:
            print(
                f"{Fore.YELLOW}No servers configured. Use 'ssh-commander add' to add servers.{Style.RESET_ALL}"
            )
            return 0

        target_servers = self.filter_servers(tags)
        if not target_servers:
            if tags:
                print(
                    f"{Fore.YELLOW}No servers found with tags: "
                    f"{', '.join(tags)}{Style.RESET_ALL}"
                )
            return 0

        _info(f"{Fore.CYAN}Executing command: {Fore.WHITE}{command}{Style.RESET_ALL}")

        def _run_for_server(server: Dict) -> Tuple[Dict, int, str, str]:
            buffer = StringIO() if parallel > 1 else None
            client, error = self._connect_to_server(
                server, strict_host_key_checking=strict_host_key_checking
            )
            if error:
                return server, 1, "", error
            session = {'client': client, 'channels': []}
            self._register_session(session)
            try:
                exit_status = self._run_one_command(client, command, out_buffer=buffer)
                return server, exit_status, buffer.getvalue() if buffer else "", ""
            finally:
                self._unregister_session(session)
                try:
                    client.close()
                except Exception:
                    pass

        failures = 0
        try:
            if parallel > 1 and len(target_servers) > 1:
                with ThreadPoolExecutor(max_workers=min(parallel, len(target_servers))) as pool:
                    futures = {pool.submit(_run_for_server, s): s for s in target_servers}
                    for future in as_completed(futures):
                        server, status, output, err = future.result()
                        header = (
                            f"\n{Fore.LIGHTBLUE_EX}=== {server['hostname']} "
                            f"({', '.join(server.get('tags', ['default']))}) ==={Style.RESET_ALL}"
                        )
                        with self._output_lock:
                            print(header)
                            if output:
                                sys.stdout.write(output)
                                if not output.endswith('\n'):
                                    sys.stdout.write('\n')
                            if err:
                                print(err)
                            if status != 0:
                                print(
                                    f"{Fore.RED}Exited with status {status}{Style.RESET_ALL}"
                                )
                        if status != 0 or err:
                            failures += 1
            else:
                for server in target_servers:
                    print(
                        f"\n{Fore.LIGHTBLUE_EX}Executing on {server['hostname']} "
                        f"({', '.join(server.get('tags', ['default']))}){Style.RESET_ALL}"
                    )
                    _, status, _, err = _run_for_server(server)
                    if err:
                        print(err)
                    if status != 0:
                        failures += 1
                        if not err:
                            print(
                                f"{Fore.RED}Command exited with status {status}{Style.RESET_ALL}"
                            )
        except KeyboardInterrupt:
            _info(f"\n{Fore.YELLOW}Command execution interrupted. Cleaning up...{Style.RESET_ALL}")
            raise
        return failures

    def run_commands_from_file(
        self,
        command_file: str,
        tags: Optional[List[str]] = None,
        parallel: int = 1,
        strict_host_key_checking: bool = False,
        stop_on_error: bool = False,
    ) -> int:
        """Execute commands from a file on servers matching the given tags."""
        if not self.servers:
            print(
                f"{Fore.YELLOW}No servers configured. Use 'ssh-commander add' to add servers.{Style.RESET_ALL}"
            )
            return 0

        try:
            with open(command_file, 'r') as f:
                commands = [
                    line.strip()
                    for line in f
                    if line.strip() and not line.lstrip().startswith('#')
                ]
        except FileNotFoundError:
            print(f"{Fore.RED}Error: Command file {command_file} not found{Style.RESET_ALL}")
            return 1

        if not commands:
            print(f"{Fore.YELLOW}Warning: No commands found in {command_file}{Style.RESET_ALL}")
            print("File should contain one command per line. Lines starting with # are ignored.")
            return 0

        target_servers = self.filter_servers(tags)
        if not target_servers:
            if tags:
                print(
                    f"{Fore.YELLOW}No servers found with tags: "
                    f"{', '.join(tags)}{Style.RESET_ALL}"
                )
            return 0

        def _run_for_server(server: Dict) -> Tuple[Dict, int, str, str]:
            buffer = StringIO() if parallel > 1 else None
            client, error = self._connect_to_server(
                server, strict_host_key_checking=strict_host_key_checking
            )
            if error:
                return server, 1, "", error
            session = {'client': client, 'channels': []}
            self._register_session(session)
            failures = 0
            try:
                for command in commands:
                    if buffer is not None:
                        buffer.write(f"{Fore.YELLOW}>>> {command}{Style.RESET_ALL}\n")
                    else:
                        with self._output_lock:
                            print(f"{Fore.YELLOW}>>> {command}{Style.RESET_ALL}", flush=True)
                    status = self._run_one_command(client, command, out_buffer=buffer)
                    if status != 0:
                        failures += 1
                        msg = f"{Fore.RED}Command exited with status {status}{Style.RESET_ALL}"
                        if buffer is not None:
                            buffer.write(msg + "\n")
                        else:
                            print(msg)
                        if stop_on_error:
                            break
                return server, failures, buffer.getvalue() if buffer else "", ""
            finally:
                self._unregister_session(session)
                try:
                    client.close()
                except Exception:
                    pass

        total_failures = 0
        try:
            if parallel > 1 and len(target_servers) > 1:
                with ThreadPoolExecutor(max_workers=min(parallel, len(target_servers))) as pool:
                    futures = {pool.submit(_run_for_server, s): s for s in target_servers}
                    for future in as_completed(futures):
                        server, failures, output, err = future.result()
                        header = (
                            f"\n{Fore.CYAN}=== {server['hostname']} "
                            f"({', '.join(server.get('tags', ['default']))}) ==={Style.RESET_ALL}"
                        )
                        with self._output_lock:
                            print(header)
                            if output:
                                sys.stdout.write(output)
                                if not output.endswith('\n'):
                                    sys.stdout.write('\n')
                            if err:
                                print(err)
                        total_failures += failures
            else:
                for server in target_servers:
                    print(
                        f"\n{Fore.CYAN}=== Executing commands on {server['hostname']} "
                        f"({', '.join(server.get('tags', ['default']))}) ==={Style.RESET_ALL}"
                    )
                    _, failures, _, err = _run_for_server(server)
                    if err:
                        print(err)
                    total_failures += failures
        except KeyboardInterrupt:
            _info(f"\n{Fore.YELLOW}Cleaning up...{Style.RESET_ALL}")
            raise
        finally:
            self.cleanup_sessions()
        return total_failures

    def test_connectivity(
        self,
        tags: Optional[List[str]] = None,
        parallel: int = 4,
        strict_host_key_checking: bool = False,
    ) -> int:
        """Test SSH connectivity to each target server. Returns failure count."""
        if not self.servers:
            print(
                f"{Fore.YELLOW}No servers configured. Use 'ssh-commander add' to add servers.{Style.RESET_ALL}"
            )
            return 0

        target_servers = self.filter_servers(tags)
        if not target_servers:
            if tags:
                print(
                    f"{Fore.YELLOW}No servers found with tags: "
                    f"{', '.join(tags)}{Style.RESET_ALL}"
                )
            return 0

        def _check(server: Dict) -> Tuple[Dict, bool, str]:
            client, error = self._connect_to_server(
                server, strict_host_key_checking=strict_host_key_checking
            )
            if error:
                return server, False, error
            try:
                # Probe with a trivial command to confirm exec works.
                _, stdout, stderr = client.exec_command('true', timeout=self.connect_timeout)
                stdout.channel.recv_exit_status()
                return server, True, ""
            except Exception as exc:
                return server, False, f"{Fore.RED}{server['hostname']}: {exc}{Style.RESET_ALL}"
            finally:
                try:
                    client.close()
                except Exception:
                    pass

        failures = 0
        worker_count = max(1, min(parallel, len(target_servers)))
        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            futures = {pool.submit(_check, s): s for s in target_servers}
            for future in as_completed(futures):
                server, ok, message = future.result()
                tags_str = ', '.join(server.get('tags', ['default']))
                if ok:
                    print(
                        f"{Fore.GREEN}OK    {Style.RESET_ALL}{server['hostname']} "
                        f"{Fore.LIGHTBLACK_EX}({tags_str}){Style.RESET_ALL}"
                    )
                else:
                    failures += 1
                    print(
                        f"{Fore.RED}FAIL  {Style.RESET_ALL}{server['hostname']} "
                        f"{Fore.LIGHTBLACK_EX}({tags_str}){Style.RESET_ALL}\n      {message}"
                    )
        return failures

    # -- server management ----------------------------------------------------

    def _find_server(self, hostname: str) -> Optional[Dict]:
        host_l = hostname.strip().lower()
        for server in self.servers:
            if str(server.get('hostname', '')).strip().lower() == host_l:
                return server
        return None

    def add_server(
        self,
        hostname: Optional[str] = None,
        username: Optional[str] = None,
        key_file: Optional[str] = None,
        password: Optional[str] = None,
        port: Optional[int] = None,
        tags: Optional[List[str]] = None,
        non_interactive: bool = False,
    ) -> None:
        """Add a new server to the configuration."""
        if not non_interactive:
            print("\nAdding a new server to the configuration")
            if not hostname:
                hostname = input("Enter hostname: ").strip()
            if not username:
                username = input("Enter username: ").strip()
            if not key_file and password is None:
                while True:
                    auth_type = input("Authentication type (key/password) [key]: ").strip().lower() or 'key'
                    if auth_type in ('key', 'k'):
                        suggestion = '~/.ssh/id_ed25519'
                        if not os.path.exists(os.path.expanduser(suggestion)):
                            suggestion = '~/.ssh/id_rsa'
                        kf = input(f"Enter path to SSH key file (default: {suggestion}): ").strip()
                        key_file = kf if kf else suggestion
                        break
                    if auth_type in ('password', 'p', 'pw'):
                        password = getpass("Enter password: ")
                        break
                    print("Please answer 'key' or 'password'.")
            if port is None:
                port_input = input("Enter SSH port (default: 22): ").strip()
                if port_input:
                    if not port_input.isdigit():
                        raise SSHCommanderError(f"Invalid port: {port_input}")
                    port = int(port_input)
            if tags is None:
                tags_input = input("Enter tags (comma-separated, default: 'default'): ").strip()
                tags = (
                    [t.strip() for t in tags_input.split(',') if t.strip()]
                    if tags_input
                    else None
                )

        if not hostname:
            raise SSHCommanderError("hostname is required")
        if not username:
            raise SSHCommanderError("username is required")
        if not key_file and password is None:
            raise SSHCommanderError("either --key-file or --password is required")

        if self._find_server(hostname):
            raise SSHCommanderError(
                f"Server '{hostname}' already exists. Use 'edit' to modify it."
            )

        server: Dict = {'hostname': hostname.strip(), 'username': username.strip()}
        if key_file:
            server['key_file'] = key_file
        else:
            server['password'] = password
        if port is not None and int(port) != 22:
            server['port'] = int(port)
        server['tags'] = tags if tags else ['default']

        self.servers.append(server)
        self._save_servers()
        print(f"\n{Fore.GREEN}Server {server['hostname']} added successfully!{Style.RESET_ALL}")

    def edit_server(
        self,
        hostname: str,
        new_hostname: Optional[str] = None,
        username: Optional[str] = None,
        key_file: Optional[str] = None,
        password: Optional[str] = None,
        port: Optional[int] = None,
        tags: Optional[List[str]] = None,
        clear_password: bool = False,
        clear_key_file: bool = False,
    ) -> bool:
        """Update fields of an existing server. Returns True on change."""
        server = self._find_server(hostname)
        if not server:
            return False

        if new_hostname:
            if (
                new_hostname.lower() != hostname.lower()
                and self._find_server(new_hostname)
            ):
                raise SSHCommanderError(
                    f"Cannot rename: server '{new_hostname}' already exists."
                )
            server['hostname'] = new_hostname.strip()
        if username:
            server['username'] = username.strip()
        if clear_password:
            server.pop('password', None)
        if clear_key_file:
            server.pop('key_file', None)
        if key_file:
            server['key_file'] = key_file
            server.pop('password', None)
        if password is not None:
            server['password'] = password
            server.pop('key_file', None)
        if port is not None:
            if int(port) == 22:
                server.pop('port', None)
            else:
                server['port'] = int(port)
        if tags is not None:
            server['tags'] = tags if tags else ['default']

        if 'key_file' not in server and 'password' not in server:
            raise SSHCommanderError(
                f"Server '{server['hostname']}' must have either a key_file or password."
            )

        self._save_servers()
        return True

    def remove_servers(self, hostnames: Iterable[str]) -> Tuple[List[str], List[str]]:
        """Remove one or more servers. Returns (removed, not_found)."""
        wanted_lower = {h.strip().lower() for h in hostnames if h and h.strip()}
        removed: List[str] = []
        kept: List[Dict] = []
        for server in self.servers:
            host = str(server.get('hostname', '')).strip()
            if host.lower() in wanted_lower:
                removed.append(host)
            else:
                kept.append(server)
        not_found = [
            h for h in hostnames if h.strip().lower() not in {r.lower() for r in removed}
        ]
        if removed:
            self.servers = kept
            self._save_servers()
        return removed, not_found

    def remove_server(self, hostname: str) -> bool:
        """Backwards-compatible single-server removal."""
        removed, _ = self.remove_servers([hostname])
        return bool(removed)

    def list_servers(self, tags: Optional[List[str]] = None, output: str = 'pretty') -> None:
        """List all configured servers."""
        servers = self.filter_servers(tags)
        if not servers:
            if tags:
                print(
                    f"{Fore.LIGHTYELLOW_EX}No servers match tags: "
                    f"{', '.join(tags)}{Style.RESET_ALL}"
                )
            else:
                print(f"{Fore.LIGHTYELLOW_EX}No servers configured.{Style.RESET_ALL}")
            return

        if output == 'json':
            import json
            print(json.dumps(servers, indent=2, default=str))
            return
        if output == 'yaml':
            print(yaml.safe_dump(servers, default_flow_style=False, sort_keys=False).rstrip())
            return
        if output == 'hosts':
            for server in servers:
                print(server['hostname'])
            return

        print(f"\n{Fore.LIGHTGREEN_EX}Configured Servers:{Style.RESET_ALL}")
        for i, server in enumerate(servers, 1):
            print(f"\n{Fore.LIGHTCYAN_EX}{i}. {server['hostname']}{Style.RESET_ALL}")
            print(f"   {Fore.LIGHTBLUE_EX}Username:{Style.RESET_ALL} {server['username']}")
            auth_type = 'Key' if 'key_file' in server else 'Password'
            auth_color = Fore.LIGHTGREEN_EX if 'key_file' in server else Fore.LIGHTYELLOW_EX
            print(
                f"   {Fore.LIGHTBLUE_EX}Auth Type:{Style.RESET_ALL} "
                f"{auth_color}{auth_type}{Style.RESET_ALL}"
            )
            if 'key_file' in server:
                print(f"   {Fore.LIGHTBLUE_EX}Key File:{Style.RESET_ALL} {server['key_file']}")
            print(f"   {Fore.LIGHTBLUE_EX}Port:{Style.RESET_ALL} {server.get('port', 22)}")
            tags_value = server.get('tags', ['default'])
            print(f"   {Fore.LIGHTBLUE_EX}Tags:{Style.RESET_ALL} {', '.join(tags_value)}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _split_tags(value: Optional[str]) -> Optional[List[str]]:
    if not value:
        return None
    parts = [t.strip() for t in value.split(',') if t.strip()]
    return parts or None


def _confirm(prompt: str, assume_yes: bool = False) -> bool:
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        # Non-interactive: refuse rather than guess.
        return False
    answer = input(f"{prompt} [y/N]: ").strip().lower()
    return answer in ('y', 'yes')


def print_examples() -> None:
    """Print usage examples with color formatting."""
    examples = [
        ("# Execute a command on all servers", "ssh-commander exec -c 'uptime'"),
        ("# Execute a command on servers with specific tags",
         "ssh-commander exec -c 'uptime' -t prod,web"),
        ("# Execute commands across servers in parallel",
         "ssh-commander exec -c 'uptime' --parallel 8"),
        ("# Execute multiple commands from a file", "ssh-commander exec -f commands.txt"),
        ("# Test SSH connectivity to all servers", "ssh-commander test"),
        ("# Add a new server interactively", "ssh-commander add"),
        ("# Add a server non-interactively (scripting)",
         "ssh-commander add -y --hostname web1.example.com --username admin "
         "--key-file ~/.ssh/id_ed25519 --tags prod,web"),
        ("# List configured servers (with optional tag filter)",
         "ssh-commander list --tag prod --output hosts"),
        ("# Edit a server",
         "ssh-commander edit web1.example.com --tags prod,web,frontend --port 2222"),
        ("# Remove one or more servers",
         "ssh-commander remove web1.example.com web2.example.com --yes"),
        ("# Sync config from a remote source",
         "ssh-commander sync https://example.com/servers.yaml --verify"),
        (None, "ssh-commander sync s3://my-bucket/servers.yaml"),
        (None, "ssh-commander sync sftp://user@host/path/servers.yaml --key-file ~/.ssh/id_rsa"),
        (None, "ssh-commander sync git+https://github.com/org/repo --branch main"),
        (None, "ssh-commander sync --dry-run /path/to/servers.yaml"),
    ]
    print(f"\n{Fore.LIGHTGREEN_EX}Examples:{Style.RESET_ALL}")
    for comment, command in examples:
        if comment:
            print(f"\n  {Fore.LIGHTCYAN_EX}{comment}{Style.RESET_ALL}")
        print(f"  {command}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='ssh-commander',
        description='SSH Commander - Execute commands on multiple servers via SSH',
        epilog='Use <command> --help for detailed help on each command',
    )
    parser.add_argument(
        '--version',
        action='version',
        version=f'ssh-commander {__version__}',
    )
    parser.add_argument(
        '--config',
        help='Path to config file (default: ~/.config/ssh-commander/servers.yaml)',
        metavar='FILE',
    )
    parser.add_argument(
        '--no-color',
        action='store_true',
        help='Disable ANSI color in output',
    )
    parser.add_argument(
        '-q', '--quiet',
        action='store_true',
        help='Suppress informational output (errors still print)',
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose output',
    )
    parser.add_argument(
        '--timeout',
        type=float,
        default=None,
        metavar='SECONDS',
        help='SSH connect timeout in seconds (default: 10)',
    )
    parser.add_argument(
        '--strict-host-key-checking',
        action='store_true',
        help='Reject unknown SSH host keys instead of auto-adding them',
    )

    subparsers = parser.add_subparsers(
        dest='command',
        title='Available Commands',
        metavar='<command>',
    )

    # exec
    exec_parser = subparsers.add_parser(
        'exec',
        help='Execute commands on servers',
        description='Execute a single command or commands from a file on servers with specified tags',
    )
    exec_group = exec_parser.add_mutually_exclusive_group(required=True)
    exec_group.add_argument(
        '-c', '--command',
        help='Single command to execute (e.g., "uptime" or "df -h")',
        metavar='CMD',
        dest='exec_command',
    )
    exec_group.add_argument(
        '-f', '--file',
        help='File containing commands to execute (one per line)',
        metavar='FILE',
        dest='exec_file',
    )
    exec_parser.add_argument(
        '-t', '--tags',
        help='Comma-separated list of tags to filter servers (default: all)',
        metavar='TAGS',
    )
    exec_parser.add_argument(
        '-p', '--parallel',
        type=int,
        default=1,
        metavar='N',
        help='Run on up to N servers in parallel (default: 1, serial)',
    )
    exec_parser.add_argument(
        '--stop-on-error',
        action='store_true',
        help='When using -f, stop running further commands on a server after the first failure',
    )

    # add
    add_parser = subparsers.add_parser(
        'add',
        help='Add a new server',
        description='Add a server to the configuration interactively or via flags',
    )
    add_parser.add_argument('--hostname', help='Server hostname')
    add_parser.add_argument('--username', help='Username for SSH login')
    auth_group = add_parser.add_mutually_exclusive_group()
    auth_group.add_argument('--key-file', help='Path to SSH private key')
    auth_group.add_argument('--password', help='Password (insecure: avoid in shell history)')
    auth_group.add_argument(
        '--password-stdin',
        action='store_true',
        help='Read password from stdin',
    )
    add_parser.add_argument('--port', type=int, help='SSH port (default: 22)')
    add_parser.add_argument('--tags', help='Comma-separated tags (default: default)')
    add_parser.add_argument(
        '-y', '--yes',
        action='store_true',
        help='Run non-interactively; require all needed flags',
    )

    # edit
    edit_parser = subparsers.add_parser(
        'edit',
        help='Edit an existing server',
        description='Modify fields of an existing server. Only provided flags are changed.',
    )
    edit_parser.add_argument('hostname', help='Hostname of the server to edit')
    edit_parser.add_argument('--rename', help='New hostname')
    edit_parser.add_argument('--username', help='New username')
    edit_parser.add_argument('--key-file', help='New SSH key file (clears any password)')
    edit_parser.add_argument('--password', help='New password (clears any key file)')
    edit_parser.add_argument('--password-stdin', action='store_true', help='Read new password from stdin')
    edit_parser.add_argument('--port', type=int, help='New SSH port')
    edit_parser.add_argument('--tags', help='Comma-separated tags (replaces existing)')
    edit_parser.add_argument(
        '--clear-password',
        action='store_true',
        help='Remove the password (must be combined with --key-file)',
    )
    edit_parser.add_argument(
        '--clear-key-file',
        action='store_true',
        help='Remove the key file (must be combined with --password)',
    )

    # list
    list_parser = subparsers.add_parser(
        'list',
        help='List configured servers',
        description='Display configured servers, optionally filtered by tags',
    )
    list_parser.add_argument('-t', '--tag', '--tags', dest='tags', help='Filter by tag(s) (comma-separated)')
    list_parser.add_argument(
        '-o', '--output',
        choices=('pretty', 'hosts', 'yaml', 'json'),
        default='pretty',
        help='Output format (default: pretty)',
    )

    # remove
    remove_parser = subparsers.add_parser(
        'remove',
        help='Remove one or more servers',
        description='Remove servers by hostname (prompts for confirmation by default)',
    )
    remove_parser.add_argument('hostnames', nargs='+', help='Hostname(s) to remove')
    remove_parser.add_argument(
        '-y', '--yes',
        action='store_true',
        help='Do not prompt for confirmation',
    )

    # test
    test_parser = subparsers.add_parser(
        'test',
        help='Test SSH connectivity to servers',
        description='Connect to each target server and verify the SSH session works',
    )
    test_parser.add_argument('-t', '--tags', help='Comma-separated tag filter')
    test_parser.add_argument('-p', '--parallel', type=int, default=4, help='Parallel workers (default: 4)')

    # sync
    sync_parser = subparsers.add_parser(
        'sync',
        help='Sync config from a URL',
        description='Download and sync config file from a URL (supports http(s), s3://, git[+...]://, sftp://, file://)',
    )
    sync_parser.add_argument(
        'url',
        help='URL to download config from (e.g., https://example.com/servers.yaml)',
    )
    sync_parser.add_argument('--dry-run', action='store_true', help='Show what would happen without making changes')
    sync_parser.add_argument('--verify', action='store_true', help='Validate YAML and entries after download')
    sync_parser.add_argument('--username', help='Username for SFTP authentication')
    sync_parser.add_argument('--key-file', help='SSH key file for SFTP/Git authentication')
    sync_parser.add_argument('--branch', help='Git branch to use (for git URLs)')
    sync_parser.add_argument(
        '--keep-backups',
        type=int,
        default=5,
        metavar='N',
        help='Number of timestamped backups to retain (default: 5)',
    )

    # config-path
    subparsers.add_parser(
        'config-path',
        help='Print the resolved config file path',
        description='Print the path that ssh-commander will read its configuration from',
    )

    # version (alias of --version, friendlier as a subcommand)
    subparsers.add_parser(
        'version',
        help='Print the version',
        description='Print the ssh-commander version',
    )

    return parser


def _read_password_stdin() -> str:
    if sys.stdin.isatty():
        # Friendlier than blocking silently.
        return getpass("Enter password: ")
    return sys.stdin.read().rstrip('\n')


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    _set_output_flags(
        quiet=getattr(args, 'quiet', False),
        verbose=getattr(args, 'verbose', False),
        no_color=getattr(args, 'no_color', False),
    )

    if not args.command:
        parser.print_help()
        print_examples()
        return 0

    try:
        commander = SSHCommander(
            config_file=args.config,
            connect_timeout=args.timeout,
        )

        if args.command == 'exec':
            tags = _split_tags(args.tags)
            if args.parallel < 1:
                print(f"{Fore.RED}Error: --parallel must be >= 1{Style.RESET_ALL}", file=sys.stderr)
                return 2
            if args.exec_command:
                failures = commander.run_command_on_all(
                    args.exec_command,
                    tags=tags,
                    parallel=args.parallel,
                    strict_host_key_checking=args.strict_host_key_checking,
                )
            else:
                if not os.path.exists(args.exec_file):
                    print(
                        f"{Fore.RED}Error: Command file '{args.exec_file}' not found{Style.RESET_ALL}",
                        file=sys.stderr,
                    )
                    print("\nExample command file format:", file=sys.stderr)
                    print("  # Check system uptime\n  uptime\n  # Check disk space\n  df -h", file=sys.stderr)
                    return 1
                failures = commander.run_commands_from_file(
                    args.exec_file,
                    tags=tags,
                    parallel=args.parallel,
                    strict_host_key_checking=args.strict_host_key_checking,
                    stop_on_error=args.stop_on_error,
                )
            return 0 if failures == 0 else 3

        elif args.command == 'add':
            password = args.password
            if args.password_stdin:
                password = _read_password_stdin()
            tags = _split_tags(args.tags)
            commander.add_server(
                hostname=args.hostname,
                username=args.username,
                key_file=args.key_file,
                password=password,
                port=args.port,
                tags=tags,
                non_interactive=args.yes,
            )
            return 0

        elif args.command == 'edit':
            password = args.password
            if args.password_stdin:
                password = _read_password_stdin()
            tags = _split_tags(args.tags)
            changed = commander.edit_server(
                hostname=args.hostname,
                new_hostname=args.rename,
                username=args.username,
                key_file=args.key_file,
                password=password,
                port=args.port,
                tags=tags,
                clear_password=args.clear_password,
                clear_key_file=args.clear_key_file,
            )
            if not changed:
                print(
                    f"{Fore.RED}Error: Server '{args.hostname}' not found{Style.RESET_ALL}",
                    file=sys.stderr,
                )
                return 1
            print(f"{Fore.GREEN}Server '{args.hostname}' updated.{Style.RESET_ALL}")
            return 0

        elif args.command == 'list':
            tags = _split_tags(args.tags)
            commander.list_servers(tags=tags, output=args.output)
            return 0

        elif args.command == 'sync':
            commander.sync_config(
                args.url,
                dry_run=args.dry_run,
                verify=args.verify,
                username=args.username,
                key_file=args.key_file,
                branch=args.branch,
                keep_backups=args.keep_backups,
            )
            return 0

        elif args.command == 'remove':
            unique_hosts = list(dict.fromkeys(args.hostnames))
            existing = [h for h in unique_hosts if commander._find_server(h)]
            missing = [h for h in unique_hosts if not commander._find_server(h)]
            if not existing:
                for h in missing:
                    print(
                        f"{Fore.RED}Error: Server '{h}' not found in configuration{Style.RESET_ALL}",
                        file=sys.stderr,
                    )
                print("\nUse 'ssh-commander list' to see configured servers", file=sys.stderr)
                return 1
            prompt = (
                f"Remove {len(existing)} server(s): " + ", ".join(existing) + "?"
            )
            if not _confirm(prompt, assume_yes=args.yes):
                print(f"{Fore.YELLOW}Aborted.{Style.RESET_ALL}")
                return 1
            removed, _ = commander.remove_servers(existing)
            for host in removed:
                print(f"{Fore.GREEN}Removed {host}{Style.RESET_ALL}")
            for host in missing:
                print(
                    f"{Fore.YELLOW}Not found: {host}{Style.RESET_ALL}",
                    file=sys.stderr,
                )
            return 0 if removed else 1

        elif args.command == 'test':
            tags = _split_tags(args.tags)
            failures = commander.test_connectivity(
                tags=tags,
                parallel=max(1, args.parallel),
                strict_host_key_checking=args.strict_host_key_checking,
            )
            return 0 if failures == 0 else 3

        elif args.command == 'config-path':
            print(commander.config_file)
            return 0

        elif args.command == 'version':
            print(f'ssh-commander {__version__}')
            return 0

        else:  # pragma: no cover - argparse already validates
            parser.print_help()
            return 1

    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Operation cancelled by user{Style.RESET_ALL}")
        return 130

    except SSHCommanderError as exc:
        print(f"{Fore.RED}Error: {exc}{Style.RESET_ALL}", file=sys.stderr)
        return 1

    except (FileNotFoundError, ValueError) as exc:
        print(f"{Fore.RED}Error: {exc}{Style.RESET_ALL}", file=sys.stderr)
        return 1

    except (socket.gaierror, socket.timeout) as exc:
        print(f"{Fore.RED}Network error: {exc}{Style.RESET_ALL}", file=sys.stderr)
        return 4

    except Exception as exc:
        print(f"{Fore.RED}Error: {exc}{Style.RESET_ALL}", file=sys.stderr)
        if _VERBOSE:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
