#!/usr/bin/env python
"""
Bump the pinned ``gws`` version, refresh ``metadata/gws_release.json`` (per-arch asset URLs +
SHA256 from the GitHub release), regenerate the whole module surface, and compute the next
extension tag.

Versioning: the extension version is ``<gws-version>.<ext-release>`` (four segments). The first
three mirror the bundled gws CLI version; the fourth is the extension's own release counter.

* A **new gws version** resets the 4th segment to ``1`` (e.g. ``0.22.6`` -> ``0.22.6.1``).
* An **extension-only change** (same gws) increments the 4th segment (``0.22.5.2`` ...).

Usage::

    python tools/update_gws.py 0.22.6            # bump to a new gws release
    python tools/update_gws.py --next-tag        # print the next tag for the current gws
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
META = os.path.join(ROOT, "src", "saltext", "gsuite", "metadata")
RELEASE_FILE = os.path.join(META, "gws_release.json")


def load_release():
    with open(RELEASE_FILE, encoding="utf-8") as handle:
        return json.load(handle)


def save_release(release):
    with open(RELEASE_FILE, "w", encoding="utf-8") as handle:
        json.dump(release, handle, indent=2)
        handle.write("\n")


def _fetch_sha256(url):
    """Fetch a ``.sha256`` sidecar for a release asset."""
    try:
        with urllib.request.urlopen(url + ".sha256", timeout=60) as resp:
            if resp.status == 200:
                return resp.read().decode("utf-8").split()[0]
    except Exception as exc:  # pylint: disable=broad-except
        print(f"  ! could not fetch {url}.sha256: {exc}", file=sys.stderr)
    return None


def refresh_shas(release):
    """Re-fetch per-arch SHA256 sidecars for the pinned version."""
    version = release["gws_version"]
    for arch, spec in release["archives"].items():
        url = release["release_url_template"].format(version=version, artifact=spec["artifact"])
        sha = _fetch_sha256(url)
        if sha:
            spec["sha256"] = sha
            print(f"  {arch}: {sha}")
        else:
            print(f"  {arch}: SHA unchanged ({spec.get('sha256')})")
    return release


def _list_tags():
    try:
        out = subprocess.run(
            ["git", "tag", "--list", "v*"],
            capture_output=True,
            text=True,
            cwd=ROOT,
            check=False,
        )
        return [t.strip().lstrip("v") for t in out.stdout.splitlines() if t.strip()]
    except OSError:
        return []


def next_tag(gws_version):
    """Compute the next ``v<gws>.<n>`` tag given existing tags."""
    prefix = gws_version + "."
    counters = []
    for tag in _list_tags():
        if tag.startswith(prefix):
            tail = tag[len(prefix) :]
            if tail.isdigit():
                counters.append(int(tail))
    nxt = (max(counters) + 1) if counters else 1
    return f"v{gws_version}.{nxt}"


def assert_tag_matches_gws(tag, release):
    """Guard: a release tag's first three segments must equal the bundled gws version."""
    version = tag.lstrip("v")
    parts = version.split(".")
    if len(parts) != 4:
        raise SystemExit(f"Tag '{tag}' must have 4 segments (<gws-version>.<ext-release>)")
    gws_from_tag = ".".join(parts[:3])
    if gws_from_tag != release["gws_version"]:
        raise SystemExit(
            f"Tag '{tag}' encodes gws {gws_from_tag}, but gws_release.json pins "
            f"{release['gws_version']}. They must not drift."
        )
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", nargs="?", help="new gws version, e.g. 0.22.6")
    parser.add_argument("--next-tag", action="store_true", help="print next tag and exit")
    parser.add_argument("--no-generate", action="store_true", help="skip running the generator")
    parser.add_argument("--check-tag", help="verify a tag matches the pinned gws version")
    args = parser.parse_args(argv)

    release = load_release()

    if args.check_tag:
        assert_tag_matches_gws(args.check_tag, release)
        print(f"OK: {args.check_tag} matches gws {release['gws_version']}")
        return

    if args.next_tag and not args.version:
        print(next_tag(release["gws_version"]))
        return

    if not args.version:
        parser.error("provide a gws version, or use --next-tag / --check-tag")

    changed = args.version != release["gws_version"]
    release["gws_version"] = args.version
    print(f"Pinning gws {args.version} and refreshing SHA256 sidecars:")
    refresh_shas(release)
    save_release(release)

    if not args.no_generate:
        print("Regenerating module surface...")
        subprocess.run(
            [sys.executable, os.path.join(ROOT, "tools", "generate_modules.py"), "--all"],
            check=True,
            cwd=ROOT,
        )

    tag = next_tag(args.version) if not changed else f"v{args.version}.1"
    print(f"\nProposed release tag: {tag}")
    print("Review the diff, then tag to cut the release.")


if __name__ == "__main__":
    main()
