#!/usr/bin/python3
"""Start the packaged RuntimeForce virtualenv as the current systemd user."""

import os
import socket
from pathlib import Path

VENV_PYTHON = Path("/opt/venvs/runtimeforce/bin/python")
PORT_MIN = 20000
PORT_COUNT = 30000


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


def main() -> None:
    if not VENV_PYTHON.is_file():
        raise RuntimeError(f"RuntimeForce Python environment is missing: {VENV_PYTHON}")

    runtime_home = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime_home:
        raise RuntimeError("XDG_RUNTIME_DIR is not set; start RuntimeForce from a logged-in user session.")

    runtime_root = Path(runtime_home)
    try:
        if runtime_root.stat().st_uid != os.getuid():
            raise RuntimeError("XDG_RUNTIME_DIR belongs to a different Linux user; do not launch RuntimeForce through sudo.")
    except OSError as exc:
        raise RuntimeError(f"Cannot access the current user's XDG_RUNTIME_DIR: {exc}") from exc

    runtime_dir = runtime_root / "runtimeforce"
    runtime_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(runtime_dir, 0o700)

    port = choose_port(os.getuid())
    port_file = runtime_dir / "port"
    temporary = runtime_dir / ".port.tmp"
    temporary.write_text(f"{port}\n", encoding="ascii")
    os.chmod(temporary, 0o600)
    temporary.replace(port_file)

    os.environ["PORT"] = str(port)
    os.environ["HOST"] = "127.0.0.1"
    os.execv(
        str(VENV_PYTHON),
        [str(VENV_PYTHON), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port), "--no-server-header"],
    )


if __name__ == "__main__":
    main()
