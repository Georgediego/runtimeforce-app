# RuntimeForce local Linux release builder

This builder runs on the developer's Ubuntu laptop. It does not use GitHub Actions or the VPS.

## Requirements

- Ubuntu 24.04, amd64
- Git and GitHub CLI (`gh`) for publishing
- Debian build tools and the dependencies declared in `debian/control`
- Docker Engine for the Snapcraft Core24 container
- A GitHub account with permission to publish releases

Install prerequisites manually; the builder never installs packages with sudo:

```bash
sudo apt update
sudo apt install -y git build-essential devscripts debhelper dh-virtualenv python3.12-dev python3.12-venv python3-pip libffi-dev libssl-dev libsqlcipher-dev docker.io
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
```

Log out and back in after adding the user to the docker group. Authenticate once:

```bash
gh auth login
gh auth status
```

## First run — build only

From any directory:

```bash
python3 ~/Runtimeforce/runtimeforce-app/packaging/release-builder/build_release.py
```

The script fetches the current `main` commit into a temporary directory, checks that CHANGELOG, Snap and DEB versions match, builds both packages, and saves them under:

```
~/.local/share/runtimeforce-release-builder/artifacts/
```

It also creates `SHA256SUMS`. The source checkout and temporary build files are removed automatically. No release is published in this mode.

Install and test both artifacts manually before enabling automated publishing.

## Publish a release manually

Only after both packages have been tested:

```bash
python3 ~/Runtimeforce/runtimeforce-app/packaging/release-builder/build_release.py --publish
```

The script refuses to overwrite an existing GitHub Release tag. It publishes the DEB, Snap and checksums together.

## Hourly automation

The accompanying systemd service and timer are intentionally not enabled by installation. Enable them only after a successful manual build and install test. The timer checks after boot and then hourly; `Persistent=true` triggers a catch-up run after the laptop was powered off.

To enable automated publishing after validation:

```bash
mkdir -p ~/.config/systemd/user
cp ~/Runtimeforce/runtimeforce-app/packaging/release-builder/systemd/runtimeforce-release-builder.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now runtimeforce-release-builder.timer
```

The laptop must be powered on and the user systemd manager active. Missed checks are caught up on the next login/boot.
