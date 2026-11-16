#!/usr/bin/python3
"""Start the per-user RuntimeForce service and open its local web interface."""

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def installed_version() -> str | None:
    changelog = Path("/usr/lib/runtimeforce/CHANGELOG.md")
    try:
        content = changelog.read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r"^##\\s+\\[?v?(\\d+\\.\\d+\\.\\d+)\\]?", content, re.MULTILINE)
    return f"v{match.group(1)}" if match else None


def running_version(port_file: Path) -> str | None:
    try:
        port = int(port_file.read_text(encoding="ascii").strip())
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v1/version", timeout=1) as response:
            payload = json.load(response)
        return payload.get("version")
    except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError):
        return None


def main() -> int:
    runtime_home = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime_home:
        print("RuntimeForce must be started from a logged-in Linux user session.", file=sys.stderr)
        return 1

    runtime_root = Path(runtime_home)
    try:
        if runtime_root.stat().st_uid != os.getuid():
            print("XDG_RUNTIME_DIR belongs to another Linux user; do not launch RuntimeForce through sudo.", file=sys.stderr)
            return 1
    except OSError as exc:
        print(f"Cannot access XDG_RUNTIME_DIR: {exc}", file=sys.stderr)
        return 1

    port_file = runtime_root / "runtimeforce" / "port"
    try:
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        active = subprocess.run(
            ["systemctl", "--user", "is-active", "--quiet", "runtimeforce.service"],
            check=False,
        ).returncode == 0
        if active and installed_version() and running_version(port_file) != installed_version():
            subprocess.run(["systemctl", "--user", "restart", "runtimeforce.service"], check=True)
        elif not active:
            subprocess.run(["systemctl", "--user", "start", "runtimeforce.service"], check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Unable to start the RuntimeForce user service: {exc}", file=sys.stderr)
        print("Check it with: journalctl --user -u runtimeforce.service -n 80", file=sys.stderr)
        return 1

    deadline = time.monotonic() + 30
    url = None
    while time.monotonic() < deadline:
        try:
            port = int(port_file.read_text(encoding="ascii").strip())
            candidate = f"http://127.0.0.1:{port}"
            with urllib.request.urlopen(candidate + "/health", timeout=1) as response:
                if response.status == 200:
                    url = candidate
                    break
        except (OSError, ValueError, urllib.error.URLError):
            time.sleep(0.5)

    if not url:
        print("RuntimeForce did not become ready within 30 seconds.", file=sys.stderr)
        print("Check it with: journalctl --user -u runtimeforce.service -n 80", file=sys.stderr)
        return 1

    print(f"RuntimeForce IDE: {url}")
    try:
        subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
