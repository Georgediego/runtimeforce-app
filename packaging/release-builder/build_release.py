#!/usr/bin/env python3
"""Build RuntimeForce Linux packages locally and optionally publish a GitHub Release."""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_URL = "https://github.com/Georgediego/runtimeforce-app.git"
SNAP_IMAGE = "ghcr.io/canonical/snapcraft:8_core24"
STATE_DIR = Path.home() / ".local/share/runtimeforce-release-builder"
ARTIFACT_DIR = STATE_DIR / "artifacts"


def run(command: list[str], *, cwd: Path | None = None, capture: bool = False) -> str:
    print("+", " ".join(command), flush=True)
    result = subprocess.run(
        command, cwd=cwd, text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    if result.returncode:
        if capture and result.stderr:
            print(result.stderr, file=sys.stderr)
        raise RuntimeError(f"Command failed ({result.returncode}): {command[0]}")
    return result.stdout.strip() if capture else ""


def extract(pattern: str, content: str, source: str) -> str:
    match = re.search(pattern, content, re.MULTILINE)
    if not match:
        raise RuntimeError(f"Cannot read version from {source}")
    return match.group(1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true", help="Publish packages to GitHub Releases")
    parser.add_argument("--repo", default=REPO_URL, help=argparse.SUPPRESS)
    args = parser.parse_args()

    os_release = Path("/etc/os-release").read_text(encoding="utf-8") if Path("/etc/os-release").exists() else ""
    if 'VERSION_ID="24.04"' not in os_release and "VERSION_ID=24.04" not in os_release:
        raise RuntimeError("This package builder currently supports Ubuntu 24.04 only.")
    if shutil.which("dpkg") and subprocess.run(["dpkg", "--print-architecture"], capture_output=True, text=True).stdout.strip() != "amd64":
        raise RuntimeError("This package builder currently creates amd64 packages only.")

    required = ["git", "dpkg", "dpkg-buildpackage", "dpkg-checkbuilddeps", "docker", "sha256sum"]
    if args.publish:
        required.append("gh")
    missing = [name for name in required if not shutil.which(name)]
    if missing:
        raise RuntimeError("Missing commands: " + ", ".join(missing))

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="runtimeforce-release-") as temp:
        temp_dir = Path(temp)
        checkout = temp_dir / "source"
        run(["git", "clone", "--filter=blob:none", "--no-checkout", args.repo, str(checkout)])
        run(["git", "fetch", "origin", "main"], cwd=checkout)
        commit = run(["git", "rev-parse", "origin/main"], cwd=checkout, capture=True)
        run(["git", "checkout", "--detach", commit], cwd=checkout)

        changelog = (checkout / "CHANGELOG.md").read_text(encoding="utf-8")
        snap_yaml = (checkout / "snap/snapcraft.yaml").read_text(encoding="utf-8")
        deb_changelog = (checkout / "debian/changelog").read_text(encoding="utf-8")
        changelog_version = extract(r"^## \[([0-9]+\.[0-9]+\.[0-9]+)\]", changelog, "CHANGELOG.md")
        snap_version = extract(r'^version:\s*["\']?([0-9]+\.[0-9]+\.[0-9]+)', snap_yaml, "snap/snapcraft.yaml")
        deb_version = extract(r"^runtimeforce \(([0-9]+\.[0-9]+\.[0-9]+)\)", deb_changelog, "debian/changelog")
        if len({changelog_version, snap_version, deb_version}) != 1:
            raise RuntimeError(
                f"Version mismatch: CHANGELOG={changelog_version}, "
                f"Snap={snap_version}, DEB={deb_version}"
            )

        version = changelog_version
        tag = f"v{version}"
        if args.publish:
            run(["gh", "auth", "status"])
            exists = subprocess.run(
                ["gh", "release", "view", tag, "--repo", "Georgediego/runtimeforce-app"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            ).returncode == 0
            if exists:
                print(f"Release {tag} already exists; refusing to overwrite it.")
                return 0

        print(f"Building RuntimeForce {version} from main commit {commit[:12]}")
        run(["dpkg-checkbuilddeps"], cwd=checkout)
        run(["dpkg-buildpackage", "-us", "-uc", "-b"], cwd=checkout)

        deb_candidates = sorted(temp_dir.glob("*.deb"))
        if not deb_candidates:
            raise RuntimeError("DEB build produced no .deb artifact.")
        deb = deb_candidates[0]
        if deb.stat().st_size < 1024:
            raise RuntimeError("DEB artifact is unexpectedly small.")

        run([
            "docker", "run", "--rm", "--user", f"{os.getuid()}:{os.getgid()}",
            "-v", f"{checkout}:/project",
            "-w", "/project",
            SNAP_IMAGE,
            "pack",
        ])
        snap_candidates = sorted(checkout.glob("*.snap"))
        if not snap_candidates:
            raise RuntimeError("Snap build produced no .snap artifact.")
        snap = snap_candidates[0]
        if snap.stat().st_size < 1024:
            raise RuntimeError("Snap artifact is unexpectedly small.")

        final_deb = ARTIFACT_DIR / f"runtimeforce_{version}_amd64.deb"
        final_snap = ARTIFACT_DIR / f"runtimeforce_{version}_amd64.snap"
        shutil.copy2(deb, final_deb)
        shutil.copy2(snap, final_snap)

    checksum_file = ARTIFACT_DIR / "SHA256SUMS"
    checksum_file.write_text(
        "".join(
            f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n"
            for path in (final_deb, final_snap)
        ),
        encoding="utf-8",
    )
    for path in (final_deb, final_snap):
        print(f"OK: {path} ({path.stat().st_size:,} bytes)")
    print(f"Checksums: {checksum_file}")

    if not args.publish:
        print("Build-only mode: nothing was uploaded. Test both packages before enabling the timer.")
        return 0

    notes = ARTIFACT_DIR / "release-notes.md"
    section = re.search(
        rf"^## \[{re.escape(version)}\].*?(?=^## \[|\Z)",
        changelog, re.MULTILINE | re.DOTALL,
    )
    notes.write_text(section.group(0).strip() if section else f"RuntimeForce {version}", encoding="utf-8")
    run([
        "gh", "release", "create", tag,
        str(final_deb), str(final_snap), str(checksum_file),
        "--repo", "Georgediego/runtimeforce-app",
        "--target", commit,
        "--title", f"RuntimeForce {tag}",
        "--notes-file", str(notes),
    ])
    print(f"Published https://github.com/Georgediego/runtimeforce-app/releases/tag/{tag}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
