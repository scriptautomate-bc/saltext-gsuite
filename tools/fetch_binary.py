#!/usr/bin/env python
"""
Build-time helper: download the pinned ``gws`` release for a target architecture, verify its
SHA256, and place the extracted binary at ``src/saltext/gsuite/_vendor/gws`` (``gws.exe`` on
Windows) so it can be bundled as package data in a platform-specific wheel.

Driven entirely by ``src/saltext/gsuite/metadata/gws_release.json`` (no network config needed
beyond GitHub release access). Used by the release CI matrix, one arch per wheel job.

Usage::

    python tools/fetch_binary.py --arch linux-x86_64
    python tools/fetch_binary.py --list
"""

import argparse
import hashlib
import io
import json
import os
import tarfile
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
META = os.path.join(ROOT, "src", "saltext", "gsuite", "metadata")
VENDOR = os.path.join(ROOT, "src", "saltext", "gsuite", "_vendor")


def load_release():
    with open(os.path.join(META, "gws_release.json"), encoding="utf-8") as handle:
        return json.load(handle)


def _download(url):
    print(f"Downloading {url}")
    with urllib.request.urlopen(url, timeout=120) as resp:
        if resp.status != 200:
            raise SystemExit(f"HTTP {resp.status} fetching {url}")
        return resp.read()


def _verify_sha256(data, expected):
    actual = hashlib.sha256(data).hexdigest()
    if expected and actual != expected:
        raise SystemExit(
            f"SHA256 mismatch!\n  expected: {expected}\n  actual:   {actual}\n"
            "Refusing to bundle an unverified binary."
        )
    return actual


def _extract(data, archive_format, member):
    if archive_format == "tar.gz":
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            for name in tar.getnames():
                if os.path.basename(name) == member:
                    extracted = tar.extractfile(name)
                    if extracted is not None:
                        return extracted.read()
            raise SystemExit(f"Member '{member}' not found in tar archive")
    if archive_format == "zip":
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for name in zf.namelist():
                if os.path.basename(name) == member:
                    return zf.read(name)
            raise SystemExit(f"Member '{member}' not found in zip archive")
    raise SystemExit(f"Unknown archive format '{archive_format}'")


def fetch(arch, release=None):
    release = release or load_release()
    archives = release["archives"]
    if arch not in archives:
        raise SystemExit(f"Unknown arch '{arch}'. Known: {', '.join(sorted(archives))}")
    spec = archives[arch]
    version = release["gws_version"]
    url = release["release_url_template"].format(version=version, artifact=spec["artifact"])

    data = _download(url)
    _verify_sha256(data, spec.get("sha256"))
    print(f"SHA256 OK ({spec.get('sha256', '<none>')})")

    binary = _extract(data, spec["archive_format"], spec["member"])
    os.makedirs(VENDOR, exist_ok=True)
    out_name = release["binary_name"]["windows" if arch.startswith("windows") else "posix"]
    out_path = os.path.join(VENDOR, out_name)
    with open(out_path, "wb") as handle:
        handle.write(binary)
    if not arch.startswith("windows"):
        os.chmod(out_path, 0o755)
    print(f"Wrote {out_path} ({len(binary)} bytes, gws {version}, {arch})")
    return out_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arch", help="target arch key from gws_release.json")
    parser.add_argument("--list", action="store_true", help="list known arch keys")
    args = parser.parse_args(argv)

    release = load_release()
    if args.list:
        print(f"gws {release['gws_version']} archives:")
        for key, spec in sorted(release["archives"].items()):
            print(f"  {key:<16} {spec['target']:<28} {spec['wheel_plat']}")
        return
    if not args.arch:
        parser.error("specify --arch <key> or --list")
    fetch(args.arch, release)


if __name__ == "__main__":
    main()
