"""
Terminal Runner Service

Executes terminal commands asynchronously with PTY support.
Manages process lifecycle, output streaming, and resource cleanup.
"""

from typing import Optional, Dict, Any, AsyncGenerator, Callable
import asyncio
import logging
import os
import signal
from datetime import datetime

logger = logging.getLogger(__name__)


class TerminalRunnerService:
    """Service for running terminal commands with async PTY support."""

    def __init__(self):
        self.active_processes: Dict[str, asyncio.subprocess.Process] = {}
        self.max_concurrent_processes = 10
        self._lock = asyncio.Lock()

    async def run_command(
        self,
        command: str,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
        shell: bool = True,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Run a terminal command and capture output.

        Args:
            command: Command to execute
            cwd: Working directory
            env: Environment variables
            timeout: Command timeout in seconds
            shell: Use shell execution
            session_id: Session identifier for tracking

        Returns:
            Dictionary with stdout, stderr, returncode, duration
        """
        start_time = datetime.utcnow()
        process_key = f"{session_id}_{id(command)}" if session_id else str(id(command))

        try:
            # Check concurrent process limit
            async with self._lock:
                if len(self.active_processes) >= self.max_concurrent_processes:
                    raise RuntimeError(
                        f"Maximum concurrent processes ({self.max_concurrent_processes}) reached"
                    )

            # Merge with current environment
            full_env = os.environ.copy()
            if env:
                full_env.update(env)

            # Start process
            process = await asyncio.create_subprocess_shell(
                command if shell else command.split()[0],
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=full_env,
                shell=shell
            )

            # Track active process
            self.active_processes[process_key] = process
            logger.debug(f"Started process {process.pid}: {command[:50]}")

            try:
                # Wait for completion with optional timeout
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )

                stdout = stdout_bytes.decode('utf-8', errors='replace') if stdout_bytes else ""
                stderr = stderr_bytes.decode('utf-8', errors='replace') if stderr_bytes else ""

                end_time = datetime.utcnow()
                duration = (end_time - start_time).total_seconds()

                result = {
                    'stdout': stdout,
                    'stderr': stderr,
                    'returncode': process.returncode or 0,
                    'duration': duration,
                    'pid': process.pid,
                    'command': command,
                    'success': process.returncode == 0
                }

                logger.debug(
                    f"Command completed: {command[:50]} "
                    f"(exit={result['returncode']}, duration={duration:.2f}s)"
                )

                return result

            except asyncio.TimeoutError:
                logger.warning(f"Command timed out after {timeout}s: {command[:50]}")
                # Kill the process
                await self._kill_process(process, process_key)
                return {
                    'stdout': '',
                    'stderr': f'Command timed out after {timeout} seconds',
                    'returncode': -1,
                    'duration': timeout,
                    'error': 'timeout',
                    'success': False
                }

        except Exception as e:
            logger.error(f"Error running command: {e}")
            return {
                'stdout': '',
                'stderr': str(e),
                'returncode': -1,
                'duration': 0,
                'error': type(e).__name__,
                'success': False
            }

        finally:
            # Remove from active processes
            async with self._lock:
                self.active_processes.pop(process_key, None)

    async def stream_command(
        self,
        command: str,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        session_id: Optional[str] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream command output in real-time.

        Args:
            command: Command to execute
            cwd: Working directory
            env: Environment variables
            session_id: Session identifier

        Yields:
            Dictionaries with output chunks
        """
        process_key = f"{session_id}_{id(command)}" if session_id else str(id(command))

        try:
            # Merge environment
            full_env = os.environ.copy()
            if env:
                full_env.update(env)

            # Start process
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=full_env,
                shell=True
            )

            self.active_processes[process_key] = process
            logger.debug(f"Started streaming process {process.pid}: {command[:50]}")

            # Stream stdout
            if process.stdout:
                async for line in process.stdout:
                    yield {
                        'type': 'stdout',
                        'data': line.decode('utf-8', errors='replace'),
                        'timestamp': datetime.utcnow().isoformat()
                    }

            # Stream stderr
            if process.stderr:
                async for line in process.stderr:
                    yield {
                        'type': 'stderr',
                        'data': line.decode('utf-8', errors='replace'),
                        'timestamp': datetime.utcnow().isoformat()
                    }

            # Wait for completion
            returncode = await process.wait()
            yield {
                'type': 'exit',
                'returncode': returncode,
                'success': returncode == 0,
                'timestamp': datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Error streaming command: {e}")
            yield {
                'type': 'error',
                'data': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }

        finally:
            async with self._lock:
                self.active_processes.pop(process_key, None)

    async def _kill_process(
        self,
        process: asyncio.subprocess.Process,
        process_key: str
    ):
        """Kill a process and clean up resources."""
        try:
            if process.returncode is None:
                # Try graceful termination first
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=3.0)
                except asyncio.TimeoutError:
                    # Force kill if still running
                    process.kill()
                    await process.wait()

            logger.debug(f"Killed process {process_key}")
        except Exception as e:
            logger.error(f"Error killing process {process_key}: {e}")

    async def kill_session_processes(self, session_id: str) -> int:
        """
        Kill all processes for a specific session.

        Args:
            session_id: Session identifier

        Returns:
            Number of processes killed
        """
        killed_count = 0
        async with self._lock:
            keys_to_kill = [
                key for key in self.active_processes.keys()
                if key.startswith(f"{session_id}_")
            ]

            for key in keys_to_kill:
                process = self.active_processes.get(key)
                if process and process.returncode is None:
                    await self._kill_process(process, key)
                    killed_count += 1

        logger.info(f"Killed {killed_count} processes for session {session_id}")
        return killed_count

    async def get_active_processes_info(self) -> list:
        """
        Get information about all active processes.

        Returns:
            List of process info dictionaries
        """
        async with self._lock:
            processes_info = []
            for key, process in self.active_processes.items():
                if process.returncode is None:  # Still running
                    processes_info.append({
                        'key': key,
                        'pid': process.pid,
                        'start_time': process._start_time if hasattr(process, '_start_time') else None,
                        'running': True
                    })
            return processes_info

    async def cleanup(self):
        """Cleanup all active processes."""
        logger.info(f"Cleaning up {len(self.active_processes)} active processes")
        
        async with self._lock:
            tasks = []
            for key, process in list(self.active_processes.items()):
                if process.returncode is None:
                    tasks.append(self._kill_process(process, key))
            
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            
            self.active_processes.clear()

    def validate_command(self, command: str) -> tuple[bool, Optional[str]]:
        """
        Validate command for safety.

        Args:
            command: Command to validate

        Returns:
            Tuple of (is_safe, error_message)
        """
        if not command or not command.strip():
            return False, "Empty command"

        # Dangerous patterns (simplified check)
        dangerous_patterns = [
            'rm -rf /',
            'mkfs',
            'dd if=/dev/zero',
            ':(){:|:&};:',
        ]

        for pattern in dangerous_patterns:
            if pattern in command.lower():
                return False, f"Dangerous command pattern detected: {pattern}"

        return True, None
