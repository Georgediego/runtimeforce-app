#!/usr/bin/python3
"""Start the per-user RuntimeForce service and open its local web interface."""

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def main() -> int:
    runtime_home = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime_home:
        print("RuntimeForce must be started from a logged-in Linux user session.", file=sys.stderr)
        return 1

    try:
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "--user", "start", "runtimeforce.service"], check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Unable to start the RuntimeForce user service: {exc}", file=sys.stderr)
        print("Check it with: journalctl --user -u runtimeforce.service -n 80", file=sys.stderr)
        return 1

    port_file = Path(runtime_home) / "runtimeforce" / "port"
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
