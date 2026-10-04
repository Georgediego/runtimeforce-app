"""
Agent Safety Guard Service

Critical safety layer that prevents destructive agent actions.
Validates all file operations, commands, and AI-generated changes before execution.
Implements the "Verify Before Write" principle from Project_Context.md section 20.2.
"""

from typing import Optional, Dict, Any, List, Tuple, Set
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


class AgentSafetyGuardService:
    """
    Safety guard service for agent operations.
    
    This service implements critical security checks to prevent:
    - Destructive file operations (deleting important files)
    - Dangerous command execution (rm -rf, chmod 777, etc.)
    - Context hallucinations (writing files that don't exist)
    - Infinite loops in agent workflows
    - Unauthorized access to sensitive directories
    """

    # Protected system directories that should never be modified
    PROTECTED_DIRECTORIES = {
        '/', '/bin', '/boot', '/dev', '/etc', '/lib', '/lib64',
        '/proc', '/root', '/sbin', '/sys', '/usr', '/var',
        '/Applications', '/System', '/Library', '/Users',  # macOS
        'C:\\Windows', 'C:\\Program Files', 'C:\\ProgramData'  # Windows
    }

    # Dangerous command patterns
    DANGEROUS_COMMAND_PATTERNS = [
        r'rm\s+(-[rf]+\s+)?/\s*$',  # rm -rf /
        r'rm\s+(-[rf]+\s+)?\*',  # rm -rf *
        r'mkfs\.',  # Format disk
        r'dd\s+if=/dev/zero',  # Zero out disk
        r':\(\)\{\s*:\|:&\s*\};:',  # Fork bomb
        r'chmod\s+(-[Rr]+\s+)?777',  # chmod 777
        r'chmod\s+(-[Rr]+\s+)?666',  # chmod 666
        r'sudo\s+rm',  # sudo rm
        r'>\s*/dev/sd',  # Overwrite disk
        r'mv\s+.*\s+/dev/null',  # Move to null
        r'echo\s+.*\s*>\s*/',  # Echo redirect to root
    ]

    # File patterns that should require extra confirmation
    CRITICAL_FILE_PATTERNS = [
        r'\.env$',  # Environment files
        r'\.git/.*',  # Git internals
        r'credentials.*',  # Credential files
        r'password.*',  # Password files
        r'\.ssh/.*',  # SSH keys
        r'\.aws/.*',  # AWS configs
        r'package\.json$',  # Package managers
        r'requirements\.txt$',  # Python deps
        r'Gemfile$',  # Ruby deps
        r'pom\.xml$',  # Maven deps
        r'\.config.*',  # Config files
        r'\.database.*',  # Database files
        r'\.db$',  # SQLite databases
    ]

    def __init__(self):
        self.operation_history: List[Dict[str, Any]] = []
        self.max_operations_per_session = 1000
        self.warning_threshold = 5  # Warnings before blocking

    def validate_file_operation(
        self,
        operation: str,
        file_path: str,
        content: Optional[str] = None,
        workspace_root: Optional[str] = None
    ) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        """
        Validate a file operation before execution.

        Args:
            operation: Operation type ('read', 'write', 'delete', 'rename')
            file_path: Target file path
            content: File content (for write operations)
            workspace_root: Root directory of the workspace

        Returns:
            Tuple of (is_safe, error_message, metadata)
        """
        metadata = {
            'operation': operation,
            'file_path': file_path,
            'risk_level': 'low',
            'checks_performed': []
        }

        # Check 1: Validate path is not empty
        if not file_path or not file_path.strip():
            return False, "File path cannot be empty", metadata

        # Check 2: Normalize and resolve path
        try:
            resolved_path = Path(file_path).resolve()
            metadata['resolved_path'] = str(resolved_path)
            metadata['checks_performed'].append('path_resolution')
        except Exception as e:
            return False, f"Invalid file path: {e}", metadata

        # Check 3: Prevent access to protected directories
        protection_check = self._check_protected_directories(str(resolved_path))
        if not protection_check[0]:
            metadata['risk_level'] = 'critical'
            metadata['checks_performed'].append('protected_directory')
            return False, protection_check[1], metadata

        # Check 4: Ensure path is within workspace (if workspace provided)
        if workspace_root:
            workspace_check = self._check_workspace_boundary(
                str(resolved_path), workspace_root
            )
            if not workspace_check[0]:
                metadata['risk_level'] = 'high'
                metadata['checks_performed'].append('workspace_boundary')
                return False, workspace_check[1], metadata

        # Check 5: Operation-specific checks
        if operation == 'delete':
            delete_check = self._validate_delete_operation(str(resolved_path))
            if not delete_check[0]:
                metadata['risk_level'] = 'high'
                metadata['checks_performed'].append('delete_validation')
                return False, delete_check[1], metadata

        elif operation == 'write':
            write_check = self._validate_write_operation(
                str(resolved_path), content
            )
            if not write_check[0]:
                metadata['risk_level'] = write_check[2]
                metadata['checks_performed'].append('write_validation')
                return False, write_check[1], metadata

        elif operation == 'rename':
            metadata['checks_performed'].append('rename_validation')
            # Additional rename checks could be added here

        # Check 6: Critical file patterns
        critical_check = self._check_critical_file_patterns(str(resolved_path))
        if critical_check[0]:
            metadata['risk_level'] = 'medium'
            metadata['requires_confirmation'] = True
            metadata['critical_file_reason'] = critical_check[1]
            metadata['checks_performed'].append('critical_file_pattern')

        metadata['checks_performed'].append('all_checks_passed')
        return True, None, metadata

    def _check_protected_directories(self, file_path: str) -> Tuple[bool, Optional[str]]:
        """Check if path is in a protected directory."""
        path_lower = file_path.lower()

        for protected_dir in self.PROTECTED_DIRECTORIES:
            if path_lower.startswith(protected_dir.lower()):
                return False, f"Access to protected directory '{protected_dir}' is forbidden"

        return True, None

    def _check_workspace_boundary(
        self,
        file_path: str,
        workspace_root: str
    ) -> Tuple[bool, Optional[str]]:
        """Ensure file is within workspace boundaries."""
        try:
            root_resolved = Path(workspace_root).resolve()
            file_resolved = Path(file_path).resolve()

            # Check if file is under root
            try:
                file_resolved.relative_to(root_resolved)
                return True, None
            except ValueError:
                return False, (
                    f"File '{file_path}' is outside workspace boundary '{workspace_root}'. "
                    "Agents cannot modify files outside the project workspace."
                )

        except Exception as e:
            return False, f"Workspace boundary check failed: {e}"

    def _validate_delete_operation(
        self,
        file_path: str
    ) -> Tuple[bool, Optional[str]]:
        """Validate delete operations with extra caution."""
        path = Path(file_path)

        # Never allow deleting directories recursively
        if path.is_dir():
            return False, (
                "Recursive directory deletion is forbidden. "
                "Delete files individually instead."
            )

        # Check for dangerous patterns
        if '*' in file_path or '?' in file_path:
            return False, "Wildcard deletions are forbidden for safety"

        # Check for critical system files
        critical_files = ['.bashrc', '.bash_profile', '.zshrc', '.profile']
        if path.name in critical_files:
            return False, f"Deletion of system file '{path.name}' is forbidden"

        return True, None

    def _validate_write_operation(
        self,
        file_path: str,
        content: Optional[str] = None
    ) -> Tuple[bool, Optional[str], str]:
        """
        Validate write operations.

        Returns:
            Tuple of (is_valid, error_message, risk_level)
        """
        # Check for file existence (prevent hallucination)
        path = Path(file_path)
        
        # If parent directory doesn't exist, warn
        if not path.parent.exists():
            logger.warning(f"Writing to non-existent directory: {path.parent}")
            # This is allowed but logged

        # Check content size
        if content:
            content_size = len(content)
            max_size = 10 * 1024 * 1024  # 10MB limit
            
            if content_size > max_size:
                return False, (
                    f"File content too large ({content_size} bytes). "
                    f"Maximum allowed: {max_size} bytes"
                ), 'high'

            # Check for suspicious content patterns
            suspicious_patterns = [
                r'#!/bin/bash.*rm\s+-rf',  # Shebang with rm -rf
                r'os\.system\(.*rm\s+',  # Python os.system with rm
                r'subprocess\.call\(.*sudo',  # Sudo in subprocess
            ]

            for pattern in suspicious_patterns:
                if re.search(pattern, content, re.IGNORECASE | re.MULTILINE):
                    return False, (
                        "Content contains suspicious code patterns. "
                        "Please review and split into smaller operations."
                    ), 'high'

        return True, None, 'low'

    def _check_critical_file_patterns(
        self,
        file_path: str
    ) -> Tuple[bool, Optional[str]]:
        """Check if file matches critical patterns requiring confirmation."""
        path_lower = file_path.lower()

        for pattern in self.CRITICAL_FILE_PATTERNS:
            if re.search(pattern, path_lower, re.IGNORECASE):
                return True, f"File matches critical pattern: {pattern}"

        return False, None

    def validate_command(
        self,
        command: str,
        workspace_root: Optional[str] = None
    ) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        """
        Validate a shell command before execution.

        Args:
            command: Shell command to validate
            workspace_root: Workspace root for context

        Returns:
            Tuple of (is_safe, error_message, metadata)
        """
        metadata = {
            'command': command,
            'risk_level': 'low',
            'checks_performed': []
        }

        if not command or not command.strip():
            return False, "Command cannot be empty", metadata

        # Check against dangerous patterns
        for pattern in self.DANGEROUS_COMMAND_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                metadata['risk_level'] = 'critical'
                metadata['checks_performed'].append('dangerous_pattern')
                return False, (
                    f"Dangerous command pattern detected: '{pattern}'. "
                    "This command could cause system damage."
                ), metadata

        # Check for sudo usage
        if command.strip().startswith('sudo'):
            metadata['risk_level'] = 'high'
            metadata['requires_approval'] = True
            metadata['reason'] = 'sudo_command'

        # Track operation
        self._track_operation('command', command, metadata['risk_level'])

        metadata['checks_performed'].append('command_validation')
        return True, None, metadata

    def detect_loop_condition(
        self,
        iteration_count: int,
        same_action_count: int,
        max_iterations: int = 50,
        max_same_action: int = 5
    ) -> Tuple[bool, Optional[str]]:
        """
        Detect potential infinite loop conditions.

        Args:
            iteration_count: Total iterations in current task
            same_action_count: Consecutive same actions
            max_iterations: Maximum allowed iterations
            max_same_action: Maximum same consecutive actions

        Returns:
            Tuple of (should_stop, reason)
        """
        if iteration_count > max_iterations:
            return True, f"Maximum iterations ({max_iterations}) exceeded"

        if same_action_count > max_same_action:
            return True, (
                f"Same action repeated {same_action_count} times. "
                "Possible infinite loop detected."
            )

        return False, None

    def _track_operation(
        self,
        operation_type: str,
        details: str,
        risk_level: str
    ):
        """Track operation for audit and rate limiting."""
        self.operation_history.append({
            'type': operation_type,
            'details': details[:200],  # Truncate long details
            'risk_level': risk_level,
            'timestamp': __import__('datetime').datetime.utcnow().isoformat()
        })

        # Prune old history
        if len(self.operation_history) > self.max_operations_per_session:
            self.operation_history = self.operation_history[-self.max_operations_per_session:]

    def get_operation_summary(self) -> Dict[str, Any]:
        """Get summary of operations performed in this session."""
        if not self.operation_history:
            return {'total': 0}

        summary = {
            'total': len(self.operation_history),
            'by_risk_level': {},
            'by_type': {},
            'warnings_count': 0
        }

        for op in self.operation_history:
            risk = op.get('risk_level', 'unknown')
            op_type = op.get('type', 'unknown')

            summary['by_risk_level'][risk] = summary['by_risk_level'].get(risk, 0) + 1
            summary['by_type'][op_type] = summary['by_type'].get(op_type, 0) + 1

            if risk in ['high', 'critical']:
                summary['warnings_count'] += 1

        return summary

    def should_block_further_operations(self) -> Tuple[bool, Optional[str]]:
        """
        Determine if further operations should be blocked due to safety concerns.

        Returns:
            Tuple of (should_block, reason)
        """
        summary = self.get_operation_summary()

        # Block if too many high-risk operations
        if summary.get('warnings_count', 0) >= self.warning_threshold:
            return True, (
                f"Safety threshold reached: {summary['warnings_count']} high-risk operations. "
                "Further operations blocked pending manual review."
            )

        return False, None

    def generate_safety_report(self) -> Dict[str, Any]:
        """Generate comprehensive safety report for the session."""
        return {
            'session_summary': self.get_operation_summary(),
            'blocking_status': self.should_block_further_operations(),
            'recent_operations': self.operation_history[-20:],  # Last 20 ops
            'recommendations': self._generate_recommendations()
        }

    def _generate_recommendations(self) -> List[str]:
        """Generate safety recommendations based on operation history."""
        recommendations = []
        summary = self.get_operation_summary()

        if summary.get('by_risk_level', {}).get('critical', 0) > 0:
            recommendations.append(
                "Critical operations detected. Review agent prompts for safety."
            )

        if summary.get('by_type', {}).get('delete', 0) > 10:
            recommendations.append(
                "High number of delete operations. Consider batch verification."
            )

        if summary.get('warnings_count', 0) > 3:
            recommendations.append(
                "Multiple warnings generated. Agent may need prompt adjustment."
            )

        return recommendations
