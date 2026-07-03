"""Tests for packaging metadata and the version<->gws consistency guard."""

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import update_gws  # noqa: E402  # pylint: disable=import-error,wrong-import-position

RELEASE = os.path.join(ROOT, "src", "saltext", "gsuite", "metadata", "gws_release.json")
SERVICES = os.path.join(ROOT, "src", "saltext", "gsuite", "metadata", "services.json")

EXPECTED_ARCHES = {
    "linux-x86_64",
    "linux-aarch64",
    "macos-x86_64",
    "macos-arm64",
    "windows-amd64",
}


def _release():
    with open(RELEASE, encoding="utf-8") as handle:
        return json.load(handle)


def test_release_metadata_has_all_arches():
    release = _release()
    assert set(release["archives"]) == EXPECTED_ARCHES
    for spec in release["archives"].values():
        assert spec["sha256"] and len(spec["sha256"]) == 64
        assert spec["artifact"]
        assert spec["wheel_plat"]


def test_services_metadata_lists_18_services():
    with open(SERVICES, encoding="utf-8") as handle:
        services = json.load(handle)["services"]
    assert len(services) == 18
    modules = {s["module"] for s in services}
    assert {"drive", "gmail", "calendar", "workflow", "modelarmor"} <= modules


def test_tag_matches_gws_ok():
    release = _release()
    gws = release["gws_version"]
    assert update_gws.assert_tag_matches_gws(f"v{gws}.1", release) is True


def test_tag_mismatch_raises():
    release = _release()
    with pytest.raises(SystemExit, match="drift"):
        update_gws.assert_tag_matches_gws("v9.9.9.1", release)


def test_tag_wrong_segment_count_raises():
    release = _release()
    gws = release["gws_version"]
    with pytest.raises(SystemExit, match="4 segments"):
        update_gws.assert_tag_matches_gws(f"v{gws}", release)


def test_next_tag_new_gws_resets_counter(monkeypatch):
    monkeypatch.setattr(update_gws, "_list_tags", lambda: ["0.22.5.1", "0.22.5.2"])
    assert update_gws.next_tag("0.22.6") == "v0.22.6.1"


def test_next_tag_same_gws_increments(monkeypatch):
    monkeypatch.setattr(update_gws, "_list_tags", lambda: ["0.22.5.1", "0.22.5.2"])
    assert update_gws.next_tag("0.22.5") == "v0.22.5.3"


def test_generated_manifest_exists_and_lists_files():
    manifest = os.path.join(
        ROOT, "src", "saltext", "gsuite", "metadata", "generated_manifest.json"
    )
    with open(manifest, encoding="utf-8") as handle:
        files = json.load(handle)["files"]
    assert any(f.endswith("modules/gsuite_drive.py") for f in files)
    assert files == sorted(files)
