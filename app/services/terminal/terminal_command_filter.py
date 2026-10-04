"""
Security Filter and Dangerous Command Classifier (Section 15.5 Invariants).
"""
import re
from typing import Tuple, Dict, Any

RISKY_COMMAND_PATTERNS = [
    (r"rm\s+(-[a-zA-Z]*[rf]|--recursive|--force)", "Recursive or force file deletion (rm -rf / rm -r)"),
    (r"chmod\s+777", "Full open permissions grant (chmod 777)"),
    (r"git\s+reset\s+--hard", "Destructive Git hard reset"),
    (r"git\s+clean\s+-[a-zA-Z]*f", "Force removal of untracked files (git clean -f)"),
    (r"pip\s+install", "Python package installation"),
    (r"npm\s+(install|i)", "Node.js package installation"),
    (r"apt(-get)?\s+install", "System package installation"),
    (r"sudo\s+", "Superuser privileged execution"),
    (r"kill\s+-9", "Force process kill"),
    (r"dd\s+if=", "Low-level disk overwrite"),
    (r"mkfs", "Filesystem format"),
]

class TerminalCommandFilter:
    @classmethod
    def evaluate_risk(cls, command: str) -> Dict[str, Any]:
        normalized = command.strip()
        if not normalized:
            return {"requires_approval": False, "risk_level": "safe", "reason": "Empty command"}

        normalized_lower = normalized.lower()

        for pattern, reason in RISKY_COMMAND_PATTERNS:
            if re.search(pattern, normalized_lower):
                return {
                    "requires_approval": True,
                    "risk_level": "high" if "sudo" in normalized_lower or "rm" in normalized_lower else "medium",
                    "reason": reason
                }

        return {"requires_approval": False, "risk_level": "safe", "reason": "Safe command"}

    @classmethod
    def is_safe(cls, command: str) -> Tuple[bool, str]:
        res = cls.evaluate_risk(command)
        if res.get("requires_approval"):
            return False, res.get("reason", "Command requires user approval")
        return True, "Safe"
