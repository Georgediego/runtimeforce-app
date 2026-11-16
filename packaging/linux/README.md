# Ubuntu package layout

The Ubuntu package is a system-wide installation. Package-owned application
files are read-only for regular users:

- Application source: `/usr/lib/runtimeforce`
- Shared Python environment: `/opt/venvs/runtimeforce`
- Per-user systemd unit: `/usr/lib/systemd/user/runtimeforce.service`
- Launcher: `/usr/share/applications/runtimeforce.desktop`

The desktop entry starts a `systemd --user` service. The service runs with the
UID, HOME, and XDG directories of the account that launched it. It does not
run as root and does not share application state between Linux accounts.

Per-user state remains in the standard locations:

- Configuration and MASTER_KEY: `$XDG_CONFIG_HOME/runtimeforce`
- SQLCipher database: `$XDG_DATA_HOME/runtimeforce`
- Runtime port file: `$XDG_RUNTIME_DIR/runtimeforce`
- Application/library caches: the respective XDG cache locations

The package must not create, chown, or migrate user data in maintainer scripts.
The first launch creates only the current user's directories and key.

The Python environment is built into the package with dh-virtualenv. The build
uses Python 3.14 and removes pip from the final shared environment so users
cannot mutate package-managed dependencies. Runtime installation does not run
pip and does not download dependencies. APT owns
updates and removal of package files; the IDE's self-updater must be disabled
for this installation method.

Build on Ubuntu 26.04 amd64:

```bash
sudo apt update
sudo apt install build-essential debhelper debhelper-compat dh-virtualenv python3.14 python3.14-venv python3-pip devscripts
dpkg-buildpackage -us -uc -b
```

The resulting binary package is written to the parent directory. Install it
with `sudo apt install ./runtimeforce_1.1.20_amd64.deb`.

This first package target is Ubuntu 26.04 amd64 only. Other Ubuntu releases and
architectures require their own builds and compatibility tests.
