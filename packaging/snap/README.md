# RuntimeForce Snap package (experimental)

This packaging target is experimental and is not published to the Snap Store yet.

## Current target

- Ubuntu desktop with Snap support, amd64.
- Snap base: Ubuntu Core 26 (core26), with Python 3.14 bundled in the Snap.
- Classic confinement is required for the IDE's user-directed terminal, Git, SSH, and arbitrary local development workspaces.
- The Snap is launched from the desktop as the logged-in user. It starts a transient per-user systemd service and opens the local web UI.
- The app's self-updater is disabled for Snap installs. Updates must come from the Snap Store.
- Existing user data remains in the normal XDG locations; the Snap launcher does not move or rewrite the database.

## Build on Ubuntu 26.04 amd64

Install Snapcraft:

```bash
sudo snap install snapcraft --classic
```

From the repository root:

```bash
snapcraft --destructive-mode
```

If Snapcraft is not installed on the build host or destructive mode is unsuitable, use the normal Snapcraft build provider:

```bash
snapcraft
```

The build should produce a .snap artifact in the project directory. The first build is a development-grade package and is not suitable for Store publication.

## Local installation test

```bash
sudo snap install --dangerous --classic ./runtimeforce_1.1.20_amd64.snap
```

Launch RuntimeForce IDE from the desktop application menu. Diagnostic commands:

```bash
systemctl --user status runtimeforce-snap.service --no-pager
journalctl --user -u runtimeforce-snap.service -n 100 --no-pager
```

Remove the test package:

```bash
sudo snap remove runtimeforce
systemctl --user stop runtimeforce-snap.service
```

## Store publication blockers

1. Register the runtimeforce name in a Snapcraft publisher account. The name may already be reserved.
2. Request approval for classic confinement from the Snap Store review team. IDEs and AI agents that execute user-directed code are listed as supported classic-confinement categories, but approval is not automatic.
3. Add a branded 512x512 store icon and complete the publisher listing (screenshots, support URL, website, privacy policy).
4. Build and test the Snap on Ubuntu 24.04 and 26.04 amd64. The current Debian package target is Ubuntu 26.04 only; this Snap target must not be advertised as Ubuntu 24.04 compatible until the test passes.
5. After review approval, change grade to stable, upload the Snap, and release it to the stable channel.

Do not upload a grade: devel build to the stable channel.