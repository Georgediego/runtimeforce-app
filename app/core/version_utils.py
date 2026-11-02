import re
from typing import Optional, Tuple


_VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def parse_version(value: str) -> Optional[Tuple[int, int, int]]:
    """Parse a semantic X.Y.Z version, accepting an optional leading v."""
    match = _VERSION_RE.fullmatch(str(value or "").strip())
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def is_newer_version(latest: str, current: str) -> bool:
    """Return True only when latest is a valid semantic version above current."""
    latest_parts = parse_version(latest)
    current_parts = parse_version(current)
    return bool(latest_parts and current_parts and latest_parts > current_parts)
