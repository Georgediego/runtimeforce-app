# RuntimeForce local Linux release builder

The builder runs on the developer's Ubuntu 24.04 amd64 laptop. It does not use GitHub Actions or the VPS. The script fetches the latest `main` itself and builds from a temporary clean checkout.

## 1. Install prerequisites

Install Debian build dependencies:

```bash
sudo apt update
sudo apt install -y git build-essential devscripts debhelper dh-virtualenv python3.12-dev python3.12-venv python3-pip libffi-dev libssl-dev libsqlcipher-dev
```

Docker must already be installed and running, and your user must be allowed to run `docker` without sudo. Do not install `docker.io` over an existing Docker CE/containerd installation.

Check:

```bash
docker --version
docker run --rm hello-world
```

Install and authenticate GitHub CLI for publishing:

```bash
gh auth login
gh auth status
```

## 2. Install builder locally

```bash
mkdir -p ~/.local/share/runtimeforce-release-builder
curl -fsSL https://raw.githubusercontent.com/Georgediego/runtimeforce-app/main/packaging/release-builder/build_release.py -o ~/.local/share/runtimeforce-release-builder/build_release.py
chmod 700 ~/.local/share/runtimeforce-release-builder/build_release.py
```

## 3. First run — build only

```bash
python3 ~/.local/share/runtimeforce-release-builder/build_release.py
```

The script checks Ubuntu 24.04 amd64, verifies that CHANGELOG, Snap and DEB versions match, builds both packages and writes SHA256 checksums to:

```
~/.local/share/runtimeforce-release-builder/artifacts/
```

No GitHub release is published in this mode. Install and test both packages manually before enabling automation.

## 4. Publish manually after successful testing

```bash
python3 ~/.local/share/runtimeforce-release-builder/build_release.py --publish
```

The script refuses to overwrite an existing release tag. DEB, Snap and SHA256SUMS are uploaded together.

## 5. Enable hourly automation only after validation

```bash
mkdir -p ~/.config/systemd/user
curl -fsSL https://raw.githubusercontent.com/Georgediego/runtimeforce-app/main/packaging/release-builder/systemd/runtimeforce-release-builder.service -o ~/.config/systemd/user/runtimeforce-release-builder.service
curl -fsSL https://raw.githubusercontent.com/Georgediego/runtimeforce-app/main/packaging/release-builder/systemd/runtimeforce-release-builder.timer -o ~/.config/systemd/user/runtimeforce-release-builder.timer
systemctl --user daemon-reload
systemctl --user enable --now runtimeforce-release-builder.timer
```

The timer runs two minutes after the user manager starts and then hourly. `Persistent=true` catches up a missed run after the laptop was powered off. The laptop must be on and the user session/systemd manager active. The service publishes automatically, so do not enable it until both package types have been installed and tested successfully.

Status and logs:

```bash
systemctl --user status runtimeforce-release-builder.timer
journalctl --user -u runtimeforce-release-builder.service -n 100 --no-pager
```

To stop automation:

```bash
systemctl --user disable --now runtimeforce-release-builder.timer
```
