"""
Intent Analyzer for extracting target entities and filtering graph query scope.
"""
import re
from typing import Dict, Any, List

class IntentAnalyzerService:
    @classmethod
    def analyze(cls, prompt: str) -> Dict[str, Any]:
        p = prompt.lower()
        
        is_ssh = any(w in p for w in ["ssh", "vps", "remote", "paramiko", "host"])
        is_git = any(w in p for w in ["git", "commit", "branch", "diff", "merge", "push"])
        is_code = any(w in p for w in ["fix", "bug", "refactor", "class", "function", "import", "error"])
        is_arch = any(w in p for w in ["architecture", "why", "decision", "design", "database"])

        target_node_types = ["File", "Class", "Function"]
        if is_ssh:
            target_node_types.extend(["TerminalCmd", "Decision"])
        if is_git:
            target_node_types.extend(["Commit", "File"])
        if is_arch:
            target_node_types.extend(["Decision", "Summary"])

        return {
            "is_ssh": is_ssh,
            "is_git": is_git,
            "is_code": is_code,
            "is_arch": is_arch,
            "target_node_types": target_node_types,
            "keywords": re.findall(r"\w+", p)
        }
