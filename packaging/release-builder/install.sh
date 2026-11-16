#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "$EUID" -ne 0 ]]; then
  echo "Run as root: curl -fsSL https://raw.githubusercontent.com/Georgediego/runtimeforce-app/main/packaging/release-builder/install.sh | sudo bash"
  exit 1
fi

if [[ ! -r /etc/os-release ]]; then
  echo "Cannot identify the operating system."
  exit 1
fi
. /etc/os-release
if [[ "$ID" != "ubuntu" || "$VERSION_ID" != "24.04" ]]; then
  echo "This release builder is configured for Ubuntu 24.04 LTS."
  exit 1
fi
if [[ "$(dpkg --print-architecture)" != "amd64" ]]; then
  echo "This release builder currently builds amd64 packages only."
  exit 1
fi

echo "[1/5] Enabling Ubuntu Universe and installing host tools..."
if [[ -f /etc/apt/sources.list.d/ubuntu.sources ]]; then
  sed -i '/^Components:/ { /universe/! s/$/ universe/; }' /etc/apt/sources.list.d/ubuntu.sources
fi
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
  ca-certificates curl git gh docker.io python3

echo "[2/5] Starting Docker..."
systemctl enable --now docker

echo "[3/5] Configuring the GitHub token..."
if [[ ! -r /dev/tty ]]; then
  echo "An interactive terminal is required to enter the GitHub token securely."
  exit 1
fi
read -r -s -p "GitHub fine-grained token (app: Contents read/write; server: Contents read): " GH_TOKEN </dev/tty
printf '\n'
if [[ -z "$GH_TOKEN" ]]; then
  echo "Token cannot be empty."
  exit 1
fi
export GH_TOKEN

echo "[4/5] Downloading the private builder securely through GitHub API..."
install -d -m 0755 /opt/runtimeforce-release-builder
GH_TOKEN="$GH_TOKEN" gh api -H "Accept: application/vnd.github.raw+json" \
  "repos/Georgediego/runtimeforce-server/contents/release-builder/release_builder.py?ref=main" \
  > /opt/runtimeforce-release-builder/release_builder.py
GH_TOKEN="$GH_TOKEN" gh api -H "Accept: application/vnd.github.raw+json" \
  "repos/Georgediego/runtimeforce-server/contents/release-builder/runtimeforce-release-builder.service?ref=main" \
  > /etc/systemd/system/runtimeforce-release-builder.service
GH_TOKEN="$GH_TOKEN" gh api -H "Accept: application/vnd.github.raw+json" \
  "repos/Georgediego/runtimeforce-server/contents/release-builder/runtimeforce-release-builder.timer?ref=main" \
  > /etc/systemd/system/runtimeforce-release-builder.timer
chmod 0755 /opt/runtimeforce-release-builder/release_builder.py
install -m 0600 /dev/null /etc/runtimeforce-release-builder.env
printf 'GH_TOKEN=%s\n' "$GH_TOKEN" > /etc/runtimeforce-release-builder.env

echo "[5/5] Enabling the 5-hour timer and starting the first build..."
systemctl daemon-reload
systemctl enable --now runtimeforce-release-builder.timer
systemctl start --no-block runtimeforce-release-builder.service

echo
echo "Builder installed. The first build is running in the background."
echo "Timer:"
systemctl list-timers runtimeforce-release-builder.timer --no-pager
echo
echo "Live build log:"
echo "  sudo journalctl -fu runtimeforce-release-builder.service"
echo
echo "Latest releases:"
gh release list --repo Georgediego/runtimeforce-app --limit 5
