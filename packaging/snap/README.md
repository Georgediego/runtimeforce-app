# RuntimeForce Snap package

This packaging target is experimental and is not published to the Snap Store yet.

## Target

- Ubuntu 24.04 LTS and newer, amd64 (runtime compatibility must be verified on each supported release).
- Snap base: Ubuntu Core 24, with Python 3.12 and application dependencies bundled.
- Classic confinement is required for the IDE's user-directed terminal, Git, SSH, and arbitrary local development workspaces.
- The desktop launcher starts a per-user systemd service and opens the local web UI.
- The app self-updater is disabled for Snap installs. Updates must come from the Snap Store.
- Existing user data remains in the normal XDG locations; the Snap launcher does not move or rewrite the database.

## Build

Snapcraft's official Linux installation normally uses the Snap Store. If the Snap Store API is unreachable on the build machine, use the official Canonical Snapcraft OCI build image instead.

With Docker installed, from the repository root:

```bash
docker run --rm --privileged \
  -v "$PWD:/build" -w /build \
  canonical/snapcraft:8_core24 snapcraft --destructive-mode
```

The build should produce a `.snap` artifact in the project directory. The first build is a development-grade package and is not suitable for Store publication.

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

## Store publication requirements

1. Register the `runtimeforce` name in a Snapcraft publisher account; availability is not yet confirmed.
2. Request and receive classic-confinement approval from the Snap Store review team. Approval is manual and not automatic.
3. Add a branded 512x512 store icon and complete the publisher listing (screenshots, support URL, website, privacy policy).
4. Build and test on Ubuntu 24.04 and 26.04 amd64.
5. After review approval, change grade to stable, upload the Snap, and release it to the stable channel.

Do not publish a `grade: devel` build to the stable channel.
