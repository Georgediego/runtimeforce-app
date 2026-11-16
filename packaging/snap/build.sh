#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(git rev-parse --show-toplevel)"
USER_UID="$(id -u)"
USER_GID="$(id -g)"

if ! command -v docker >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y docker.io
fi

sudo systemctl start docker

# Canonical publishes the supported Snapcraft OCI images on GHCR,
# not Docker Hub. This image matches base: core24.
sudo docker run --rm \
  -v "$ROOT:/project" \
  -w /project \
  ghcr.io/canonical/snapcraft:8_core24 \
  pack

for path in parts stage prime; do
  if [ -d "$ROOT/$path" ]; then
    sudo chown -R "$USER_UID:$USER_GID" "$ROOT/$path"
  fi
done

find "$ROOT" -maxdepth 1 -type f -name '*.snap' \
  -exec sudo chown "$USER_UID:$USER_GID" {} +

echo
echo "Snap build finished. Artifact(s):"
find "$ROOT" -maxdepth 1 -type f -name '*.snap' -printf '%f\n'
