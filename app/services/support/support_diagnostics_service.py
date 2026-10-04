"""
Support Diagnostics Service

Collects diagnostic information for support tickets.
Gathers system info, logs, and configuration safely without exposing secrets.
"""

from typing import Dict, Any, List, Optional
import platform
import sys
import os
import logging
from datetime import datetime
import json

logger = logging.getLogger(__name__)


class SupportDiagnosticsService:
    """Service for collecting diagnostic information for support."""

    # Sensitive keys to filter from logs/configs
    SENSITIVE_PATTERNS = [
        'password',
        'secret',
        'token',
        'key',
        'api_key',
        'apikey',
        'credential',
        'private',
        'auth',
    ]

    def __init__(self):
        pass

    def collect_system_info(self) -> Dict[str, Any]:
        """
        Collect basic system information.

        Returns:
            Dictionary with system information
        """
        try:
            return {
                'platform': platform.system(),
                'platform_version': platform.version(),
                'machine': platform.machine(),
                'processor': platform.processor(),
                'python_version': sys.version,
                'python_implementation': platform.python_implementation(),
                'cwd': os.getcwd(),
                'timestamp': datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Error collecting system info: {e}")
            return {'error': str(e)}

    def collect_runtime_info(self) -> Dict[str, Any]:
        """
        Collect runtime environment information.

        Returns:
            Dictionary with runtime information
        """
        try:
            info = {
                'argv': sys.argv[:1] if sys.argv else [],  # Only script name
                'path': sys.path[:5],  # First 5 paths
                'modules_loaded': len(sys.modules),
            }

            # Environment variables (filtered)
            env_info = {}
            sensitive_vars = ['PASSWORD', 'SECRET', 'TOKEN', 'KEY', 'CREDENTIAL', 'AUTH']

            for key, value in os.environ.items():
                is_sensitive = any(
                    pattern in key.lower()
                    for pattern in self.SENSITIVE_PATTERNS
                )
                if not is_sensitive:
                    # Only include non-sensitive vars
                    env_info[key] = self._sanitize_value(value)

            info['env_count'] = len(env_info)
            info['env_sample'] = dict(list(env_info.items())[:10])  # First 10

            return info
        except Exception as e:
            logger.error(f"Error collecting runtime info: {e}")
            return {'error': str(e)}

    def _sanitize_value(self, value: str, max_length: int = 50) -> str:
        """
        Sanitize a value by truncating and masking.

        Args:
            value: Value to sanitize
            max_length: Maximum length to keep

        Returns:
            Sanitized value
        """
        if not isinstance(value, str):
            value = str(value)

        # Truncate long values
        if len(value) > max_length:
            value = value[:max_length] + '...'

        return value

    def collect_error_context(
        self,
        error: Exception,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Collect error context for debugging.

        Args:
            error: Exception object
            context: Additional context dictionary

        Returns:
            Dictionary with error information
        """
        try:
            error_info = {
                'type': type(error).__name__,
                'message': str(error),
                'args': [str(arg) for arg in error.args[:5]],  # First 5 args
                'timestamp': datetime.utcnow().isoformat()
            }

            if context:
                sanitized_context = {}
                for key, value in context.items():
                    # Skip sensitive keys
                    is_sensitive = any(
                        pattern in key.lower()
                        for pattern in self.SENSITIVE_PATTERNS
                    )
                    if not is_sensitive:
                        sanitized_context[key] = self._sanitize_value(str(value))

                error_info['context'] = sanitized_context

            return error_info
        except Exception as e:
            logger.error(f"Error collecting error context: {e}")
            return {'error': str(e)}

    def collect_log_snippet(
        self,
        log_file_path: Optional[str] = None,
        lines: int = 50,
        level_filter: Optional[str] = None
    ) -> List[str]:
        """
        Collect recent log entries.

        Args:
            log_file_path: Path to log file (if None, uses memory handler)
            lines: Number of lines to collect
            level_filter: Filter by log level ('ERROR', 'WARNING', etc.)

        Returns:
            List of log lines
        """
        log_lines = []

        try:
            if log_file_path and os.path.exists(log_file_path):
                with open(log_file_path, 'r') as f:
                    all_lines = f.readlines()
                    recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines

                    for line in recent_lines:
                        # Filter by level if specified
                        if level_filter and level_filter not in line:
                            continue

                        # Sanitize sensitive information
                        sanitized_line = self._sanitize_log_line(line)
                        log_lines.append(sanitized_line)
            else:
                # Collect from memory handlers or return empty
                log_lines = ["Log file not available"]

        except Exception as e:
            logger.error(f"Error collecting log snippet: {e}")
            log_lines.append(f"Error: {str(e)}")

        return log_lines

    def _sanitize_log_line(self, line: str) -> str:
        """
        Sanitize a log line by masking sensitive patterns.

        Args:
            line: Log line to sanitize

        Returns:
            Sanitized log line
        """
        sanitized = line

        # Mask common sensitive patterns
        import re

        # API keys (generic)
        sanitized = re.sub(
            r'(api[_-]?key|apikey)\s*[=:]\s*["\']?[a-zA-Z0-9_-]{20,}["\']?',
            r'\1=[REDACTED]',
            sanitized,
            flags=re.IGNORECASE
        )

        # Tokens
        sanitized = re.sub(
            r'(token|secret)\s*[=:]\s*["\']?[a-zA-Z0-9_-]{20,}["\']?',
            r'\1=[REDACTED]',
            sanitized,
            flags=re.IGNORECASE
        )

        # Passwords
        sanitized = re.sub(
            r'(password|passwd)\s*[=:]\s*["\']?[^"\'\s]+["\']?',
            r'\1=[REDACTED]',
            sanitized,
            flags=re.IGNORECASE
        )

        return sanitized

    def generate_diagnostics_report(
        self,
        include_logs: bool = True,
        log_file_path: Optional[str] = None,
        error_context: Optional[Dict[str, Any]] = None,
        custom_fields: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate comprehensive diagnostics report.

        Args:
            include_logs: Whether to include log snippets
            log_file_path: Path to log file
            error_context: Error context if reporting an issue
            custom_fields: Custom fields to include

        Returns:
            Complete diagnostics report dictionary
        """
        report = {
            'report_version': '1.0',
            'generated_at': datetime.utcnow().isoformat(),
            'system': self.collect_system_info(),
            'runtime': self.collect_runtime_info(),
        }

        if error_context:
            report['error'] = error_context

        if include_logs:
            report['logs'] = self.collect_log_snippet(
                log_file_path=log_file_path,
                lines=50,
                level_filter='ERROR'
            )

        if custom_fields:
            # Sanitize custom fields
            sanitized_custom = {}
            for key, value in custom_fields.items():
                is_sensitive = any(
                    pattern in str(key).lower()
                    for pattern in self.SENSITIVE_PATTERNS
                )
                if not is_sensitive:
                    sanitized_custom[key] = self._sanitize_value(str(value))

            report['custom'] = sanitized_custom

        return report

    def export_diagnostics_json(
        self,
        output_path: str,
        include_logs: bool = True,
        log_file_path: Optional[str] = None
    ) -> bool:
        """
        Export diagnostics report to JSON file.

        Args:
            output_path: Path to output JSON file
            include_logs: Whether to include logs
            log_file_path: Path to log file

        Returns:
            True if successful, False otherwise
        """
        try:
            report = self.generate_diagnostics_report(
                include_logs=include_logs,
                log_file_path=log_file_path
            )

            with open(output_path, 'w') as f:
                json.dump(report, f, indent=2, default=str)

            logger.info(f"Diagnostics exported to {output_path}")
            return True

        except Exception as e:
            logger.error(f"Error exporting diagnostics: {e}")
            return False

    def get_support_ticket_summary(
        self,
        ticket_id: str,
        description: str,
        severity: str = 'medium'
    ) -> Dict[str, Any]:
        """
        Generate a summary for a support ticket.

        Args:
            ticket_id: Ticket identifier
            description: User-provided description
            severity: Ticket severity ('low', 'medium', 'high', 'critical')

        Returns:
            Ticket summary dictionary
        """
        return {
            'ticket_id': ticket_id,
            'severity': severity,
            'description': self._sanitize_value(description, max_length=500),
            'diagnostics': self.generate_diagnostics_report(
                include_logs=True,
                error_context={'description': description}
            ),
            'created_at': datetime.utcnow().isoformat()
        }
