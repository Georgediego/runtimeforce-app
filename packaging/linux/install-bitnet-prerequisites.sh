#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
    exec sudo "$0" "$@"
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y build-essential cmake git clang-18 python3-dev python3-venv

if ! command -v clang-18 >/dev/null 2>&1 || ! command -v clang++-18 >/dev/null 2>&1; then
    echo "Clang 18 compiler packages are required for bitnet.cpp." >&2
    exit 1
fi

echo "BitNet build prerequisites installed. Open RuntimeForce → Settings → Providers → Local Models to download a model."
