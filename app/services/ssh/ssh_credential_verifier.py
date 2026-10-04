"""
SSH Credential Verifier Service

Validates SSH credentials (password and key-based) for remote connections.
Tests connectivity before saving credentials to the database.
"""

from typing import Optional, Tuple, Dict, Any
import asyncio
import logging
import paramiko
import socket

logger = logging.getLogger(__name__)


class SSHCredentialVerifier:
    """Service for verifying SSH credentials before storage."""

    DEFAULT_SSH_PORT = 22
    CONNECTION_TIMEOUT = 10
    AUTH_TIMEOUT = 5

    def __init__(self):
        pass

    async def verify_password_auth(
        self,
        host: str,
        port: int,
        username: str,
        password: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Verify SSH password authentication.

        Args:
            host: SSH host address
            port: SSH port
            username: SSH username
            password: SSH password

        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Validate inputs first
            validation_error = self._validate_ssh_params(host, port, username)
            if validation_error:
                return False, validation_error

            # Run blocking SSH connection in executor
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._test_password_auth_sync,
                host, port, username, password
            )
            return result

        except asyncio.TimeoutError:
            logger.warning(f"SSH password auth timeout for {username}@{host}:{port}")
            return False, "Connection timed out"
        except Exception as e:
            logger.error(f"Error verifying SSH password auth: {e}")
            return False, str(e)

    def _test_password_auth_sync(
        self,
        host: str,
        port: int,
        username: str,
        password: str
    ) -> Tuple[bool, Optional[str]]:
        """Synchronous SSH password authentication test."""
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            client.connect(
                hostname=host,
                port=port,
                username=username,
                password=password,
                timeout=self.AUTH_TIMEOUT,
                allow_agent=False,
                look_for_keys=False,
                banner_timeout=self.CONNECTION_TIMEOUT
            )

            # Test basic command execution
            stdin, stdout, stderr = client.exec_command('echo "connection_test"')
            exit_status = stdout.channel.recv_exit_status()

            if exit_status == 0:
                logger.info(f"SSH password auth successful for {username}@{host}:{port}")
                return True, None
            else:
                return False, "Command execution failed"

        except paramiko.AuthenticationException:
            logger.warning(f"SSH authentication failed for {username}@{host}:{port}")
            return False, "Authentication failed: invalid username or password"
        except paramiko.SSHException as e:
            logger.error(f"SSH error for {username}@{host}:{port}: {e}")
            return False, f"SSH error: {str(e)}"
        except socket.timeout:
            return False, "Connection timed out"
        except socket.error as e:
            logger.error(f"Socket error for {username}@{host}:{port}: {e}")
            return False, f"Network error: {str(e)}"
        finally:
            client.close()

    async def verify_key_auth(
        self,
        host: str,
        port: int,
        username: str,
        private_key: str,
        passphrase: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Verify SSH key-based authentication.

        Args:
            host: SSH host address
            port: SSH port
            username: SSH username
            private_key: SSH private key content (PEM format)
            passphrase: Optional passphrase for encrypted key

        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Validate inputs
            validation_error = self._validate_ssh_params(host, port, username)
            if validation_error:
                return False, validation_error

            if not private_key or not private_key.strip():
                return False, "Private key is empty"

            # Run blocking SSH connection in executor
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._test_key_auth_sync,
                host, port, username, private_key, passphrase
            )
            return result

        except asyncio.TimeoutError:
            logger.warning(f"SSH key auth timeout for {username}@{host}:{port}")
            return False, "Connection timed out"
        except Exception as e:
            logger.error(f"Error verifying SSH key auth: {e}")
            return False, str(e)

    def _test_key_auth_sync(
        self,
        host: str,
        port: int,
        username: str,
        private_key: str,
        passphrase: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """Synchronous SSH key authentication test."""
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            # Load private key from string
            key_file = None
            key_types = [
                paramiko.RSAKey,
                paramiko.DSSKey,
                paramiko.Ed25519Key,
                paramiko.ECDSAKey
            ]

            key_loaded = None
            for key_type in key_types:
                try:
                    key_file = key_type.from_private_key_string(
                        private_key,
                        password=passphrase
                    )
                    key_loaded = key_type
                    break
                except paramiko.SSHException:
                    continue

            if not key_file:
                return False, "Invalid private key format or unsupported key type"

            # Connect with key
            client.connect(
                hostname=host,
                port=port,
                username=username,
                pkey=key_file,
                timeout=self.AUTH_TIMEOUT,
                allow_agent=False,
                look_for_keys=False,
                banner_timeout=self.CONNECTION_TIMEOUT
            )

            # Test basic command execution
            stdin, stdout, stderr = client.exec_command('echo "connection_test"')
            exit_status = stdout.channel.recv_exit_status()

            if exit_status == 0:
                logger.info(f"SSH key auth successful for {username}@{host}:{port}")
                return True, None
            else:
                return False, "Command execution failed"

        except paramiko.AuthenticationException:
            logger.warning(f"SSH key authentication failed for {username}@{host}:{port}")
            return False, "Authentication failed: key not authorized"
        except paramiko.PasswordRequiredException:
            return False, "Private key requires a passphrase"
        except paramiko.SSHException as e:
            logger.error(f"SSH error for {username}@{host}:{port}: {e}")
            return False, f"SSH error: {str(e)}"
        except socket.timeout:
            return False, "Connection timed out"
        except socket.error as e:
            logger.error(f"Socket error for {username}@{host}:{port}: {e}")
            return False, f"Network error: {str(e)}"
        finally:
            client.close()

    def _validate_ssh_params(
        self,
        host: str,
        port: int,
        username: str
    ) -> Optional[str]:
        """Validate basic SSH parameters."""
        if not host or not host.strip():
            return "Host is required"

        if not username or not username.strip():
            return "Username is required"

        if not isinstance(port, int) or port < 1 or port > 65535:
            return "Invalid port number (must be 1-65535)"

        # Basic hostname/IP validation
        import re
        ip_pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
        hostname_pattern = r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$'

        if not (re.match(ip_pattern, host) or re.match(hostname_pattern, host)):
            return "Invalid hostname or IP address format"

        return None

    async def check_host_reachability(
        self,
        host: str,
        port: int = DEFAULT_SSH_PORT
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if SSH host is reachable (without authentication).

        Args:
            host: SSH host address
            port: SSH port

        Returns:
            Tuple of (reachable, error_message)
        """
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._check_tcp_connection_sync,
                host, port
            )
            return result
        except Exception as e:
            logger.error(f"Error checking host reachability: {e}")
            return False, str(e)

    def _check_tcp_connection_sync(
        self,
        host: str,
        port: int
    ) -> Tuple[bool, Optional[str]]:
        """Synchronous TCP connection check."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.CONNECTION_TIMEOUT)

        try:
            result = sock.connect_ex((host, port))
            if result == 0:
                logger.debug(f"Host {host}:{port} is reachable")
                return True, None
            else:
                return False, f"Host unreachable (error code: {result})"
        except socket.timeout:
            return False, "Connection timed out"
        except socket.gaierror:
            return False, "Hostname resolution failed"
        except socket.error as e:
            return False, f"Network error: {str(e)}"
        finally:
            sock.close()

    def get_key_type_info(self, private_key: str) -> Dict[str, Any]:
        """
        Get information about an SSH private key.

        Args:
            private_key: Private key content

        Returns:
            Dictionary with key information
        """
        info = {
            'type': 'unknown',
            'bits': 0,
            'is_encrypted': False,
            'fingerprint': None
        }

        key_types = [
            ('RSA', paramiko.RSAKey),
            ('DSS', paramiko.DSSKey),
            ('Ed25519', paramiko.Ed25519Key),
            ('ECDSA', paramiko.ECDSAKey)
        ]

        for key_name, key_class in key_types:
            try:
                key = key_class.from_private_key_string(private_key)
                info['type'] = key_name
                info['bits'] = key.get_bits() if hasattr(key, 'get_bits') else 0
                
                # Get fingerprint
                fingerprint = key.get_fingerprint().hex()
                info['fingerprint'] = f"{fingerprint[:16]}..."
                
                break
            except paramiko.PasswordRequiredException:
                info['is_encrypted'] = True
                continue
            except paramiko.SSHException:
                continue

        return info
