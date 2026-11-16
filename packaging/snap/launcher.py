#!/usr/bin/env python3
"""Launch RuntimeForce as a per-user systemd service from the Snap package."""

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

SERVICE = "runtimeforce-snap.service"
PORT_MIN = 21000
PORT_COUNT = 30000


def service_active() -> bool:
    return subprocess.run(["systemctl", "--user", "is-active", "--quiet", SERVICE], check=False).returncode == 0


def healthy(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def choose_port(uid: int) -> int:
    preferred = PORT_MIN + (uid % PORT_COUNT)
    for offset in range(PORT_COUNT):
        port = PORT_MIN + ((preferred - PORT_MIN + offset) % PORT_COUNT)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("No available localhost port for RuntimeForce.")


def main() -> int:
    snap_root = Path(os.environ.get("SNAP", "")).resolve()
    if not snap_root.is_dir():
        print("RuntimeForce must be launched from its installed Snap package.", file=sys.stderr)
        return 1

    runtime_home = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime_home:
        print("RuntimeForce must be started from a logged-in desktop session.", file=sys.stderr)
        return 1

    runtime_root = Path(runtime_home)
    if runtime_root.stat().st_uid != os.getuid():
        print("XDG_RUNTIME_DIR belongs to another user; do not launch RuntimeForce through sudo.", file=sys.stderr)
        return 1

    runtime_dir = runtime_root / "runtimeforce-snap"
    runtime_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(runtime_dir, 0o700)
    port_file = runtime_dir / "port"

    port = None
    try:
        candidate = int(port_file.read_text(encoding="ascii").strip())
        if service_active() and healthy(candidate):
            port = candidate
    except (OSError, ValueError):
        pass

    if port is None:
        if service_active():
            subprocess.run(["systemctl", "--user", "stop", SERVICE], check=False)
        port = choose_port(os.getuid())
        command = [
            "systemd-run", "--user", "--unit=runtimeforce-snap", "--collect",
            "--property=Restart=on-failure", "--property=RestartSec=5",
            f"--setenv=PYTHONPATH={snap_root}", "--setenv=PYTHONUNBUFFERED=1",
            "--setenv=SNAP_NAME=runtimeforce", f"--setenv=SNAP={snap_root}",
            str(snap_root / "venv/bin/python"), "-m", "uvicorn", "app.main:app",
            "--host", "127.0.0.1", "--port", str(port), "--no-server-header",
        ]
        try:
            subprocess.run(command, check=True, timeout=15)
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            print(f"Unable to start RuntimeForce: {exc}", file=sys.stderr)
            print("Inspect logs with: journalctl --user -u runtimeforce-snap -n 80", file=sys.stderr)
            return 1

        temporary = runtime_dir / ".port.tmp"
        temporary.write_text(f"{port}\n", encoding="ascii")
        os.chmod(temporary, 0o600)
        temporary.replace(port_file)

    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if healthy(port):
            url = f"http://127.0.0.1:{port}"
            print(f"RuntimeForce IDE: {url}")
            subprocess.Popen([ "xdg-open", url ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return 0
        time.sleep(0.5)

    print("RuntimeForce did not become ready within 30 seconds.", file=sys.stderr)
    print("Inspect logs with: journalctl --user -u runtimeforce-snap -n 80", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
