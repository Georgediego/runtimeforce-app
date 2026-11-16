#!/bin/sh
set -eu
exec "$SNAP/venv/bin/python" "$SNAP/packaging/snap/launcher.py" "$@"
