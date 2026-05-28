"""
FuzzyPatcher: smart code modification via SEARCH/REPLACE blocks.
Uses fuzzy matching (difflib) to locate context in changed files.
"""
import difflib
import os
import logging
from typing import Dict, Any, List, Tuple, Optional

logger = logging.getLogger("ai_runtime.tools.patch")


def apply_patch(filepath: str, patch_content: str) -> Dict[str, Any]:
    """
    Apply patch in format:
    <<<<<<< SEARCH
    [old code]
    =======
    [new code]
    >>>>>>> REPLACE
    """
    if not os.path.exists(filepath):
        return {"error": f"File does not exist: {filepath}"}
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            original_lines = f.readlines()
    except Exception as e:
        return {"error": f"File read error: {e}"}
    blocks = []
    current_block = {"search": [], "replace": [], "mode": None}
    for line in patch_content.splitlines(keepends=True):
        if line.startswith("<<<<<<< SEARCH"):
            current_block["mode"] = "search"
        elif line.startswith("======="):
            current_block["mode"] = "replace"
        elif line.startswith(">>>>>>> REPLACE"):
            blocks.append(current_block)
            current_block = {"search": [], "replace": [], "mode": None}
        else:
            if current_block["mode"] == "search":
                current_block["search"].append(line)
            elif current_block["mode"] == "replace":
                current_block["replace"].append(line)
    if not blocks:
        return {"error": "No SEARCH/REPLACE blocks found in patch"}
    modified_lines = list(original_lines)
    applied_count = 0
    for block in blocks:
        search_lines = block["search"]
        replace_lines = block["replace"]
        if not search_lines:
            continue
        found_idx = _find_fuzzy_block(modified_lines, search_lines)
        if found_idx is not None:
            start, end = found_idx
            modified_lines = modified_lines[:start] + replace_lines + modified_lines[end:]
            applied_count += 1
        else:
            return {
                "error": f"SEARCH block not found in file (threshold 0.8):\n{''.join(search_lines[:5])}...",
                "partial_applied": applied_count
            }
    try:
        dir_name = os.path.dirname(filepath)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.writelines(modified_lines)
        return {
            "status": "success",
            "applied_blocks": applied_count,
            "diff": _generate_diff(original_lines, modified_lines)
        }
    except Exception as e:
        return {"error": f"File write error: {e}"}


def _find_fuzzy_block(lines: List[str], search_block: List[str], threshold: float = 0.8) -> Optional[Tuple[int, int]]:
    """Find a block in lines with allowed deviation (fuzzy)."""
    search_len = len(search_block)
    if search_len == 0:
        return None
    for i in range(len(lines) - search_len + 1):
        candidate = lines[i:i + search_len]
        similarity = difflib.SequenceMatcher(None, search_block, candidate).ratio()
        if similarity >= threshold:
            return (i, i + search_len)
    return None


def _generate_diff(old_lines: List[str], new_lines: List[str]) -> str:
    """Generate diff for debugging."""
    diff = difflib.unified_diff(old_lines, new_lines, fromfile="a", tofile="b", lineterm="")
    return "".join(diff)


class FuzzyPatcher:
    """Legacy alias."""
    @staticmethod
    def apply_patch(filepath: str, patch_content: str) -> Dict[str, Any]:
        return apply_patch(filepath, patch_content)
