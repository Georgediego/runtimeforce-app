# RuntimeForce Snap package

## Target

- Ubuntu 24.04 LTS and newer, amd64 (runtime compatibility must be verified on each supported release).
- Snap base: Ubuntu Core 24, with Python 3.12 and application dependencies bundled.
- Classic confinement is required for the IDE's user-directed terminal, Git, SSH, and arbitrary local development workspaces.
- The desktop launcher starts a per-user systemd service and opens the local web UI.
- Existing user data remains in the normal XDG locations; the Snap launcher does not move or rewrite the database.

## Build

The repository includes a Docker-based build script using Canonical's Snapcraft 8 / Core 24 build image:

```bash
bash packaging/snap/build.sh
```

The first build may take several minutes. The resulting package is a local-install build, not a Snap Store publication.

## Local installation test

```bash
sudo snap install --dangerous --classic ./runtimeforce_1.1.20_amd64.snap
```

Launch RuntimeForce IDE from the desktop application menu. Diagnostics:

```bash
systemctl --user status runtimeforce-snap.service --no-pager
journalctl --user -u runtimeforce-snap.service -n 80 --no-pager
```

Remove the test package:

```bash
sudo snap remove runtimeforce
systemctl --user stop runtimeforce-snap.service
```

## Snap Store publication

The Snap Store name and classic-confinement approval must be confirmed with the publisher account. Do not publish a `grade: devel` build to a stable channel. The GitHub Release is the distribution point for the tested local-install package.
