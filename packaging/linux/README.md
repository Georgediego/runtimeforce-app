# RuntimeForce Linux DEB package

## Target

- Ubuntu 24.04 LTS, amd64.
- Python 3.12, matching the Ubuntu 24.04 system runtime.
- The package installs the application under `/usr/lib/runtimeforce` and its private Python environment under `/opt/venvs/runtimeforce`.
- RuntimeForce runs as the logged-in desktop user through a systemd user service. It is not started as root.
- The launcher opens the local web interface after the service becomes healthy.
- The original application logo at `app/static/logo.png` is installed as the desktop icon.
- User databases, settings, API keys, projects, and workspaces are not stored inside package-owned directories.

## Build

The automated VPS builder creates the DEB inside an Ubuntu 24.04 Docker container. To build manually on Ubuntu 24.04:

```bash
sudo apt-get update
sudo apt-get install -y build-essential debhelper dh-virtualenv python3.12 python3.12-dev python3.12-venv python3-pip libffi-dev libssl-dev libsqlcipher-dev
dpkg-buildpackage -us -uc -b
```

The resulting `.deb` is created in the parent directory.

## Install and launch

```bash
sudo apt install ./runtimeforce_1.1.21_amd64.deb
```

Launch **RuntimeForce IDE** from the desktop application menu. The launcher starts the per-user service and opens its local URL.

Diagnostics:

```bash
systemctl --user status runtimeforce.service --no-pager
journalctl --user -u runtimeforce.service -n 80 --no-pager
```

## BitNet local inference

Optional BitNet support requires a one-time compiler setup and model download. Install prerequisites with:

```bash
sudo bash /usr/share/runtimeforce/install-bitnet-prerequisites.sh
```

Then open Settings → Providers → Local Models and select **Download & Build**. See `docs/BITNET.md` for CPU compatibility, model storage, and runtime details.

## Remove

```bash
sudo apt remove runtimeforce
```

Removing the package does not delete user-owned application data.
