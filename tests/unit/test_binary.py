import os
import stat
import subprocess
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from saltext.gsuite import _binary


def test_binary_name_posix():
    with patch.object(_binary.sys, "platform", "linux"):
        assert _binary.binary_name() == "gws"


def test_binary_name_windows():
    with patch.object(_binary.sys, "platform", "win32"):
        assert _binary.binary_name() == "gws.exe"


def test_override_from_pillar_wins(tmp_path):
    fake = tmp_path / "gws"
    fake.write_text("#!/bin/sh\n")
    pillar = {"gsuite": {"binary_path": str(fake)}}
    assert _binary.resolve(pillar=pillar) == str(fake)


def test_override_missing_raises(tmp_path):
    pillar = {"gsuite": {"binary_path": str(tmp_path / "nope")}}
    with pytest.raises(_binary.BinaryError, match="binary_path"):
        _binary.resolve(pillar=pillar)


def test_resolve_bundled_missing_raises(tmp_path):
    with patch.object(_binary, "_bundled_path", return_value=str(tmp_path / "missing")):
        with pytest.raises(_binary.BinaryError, match="bundled 'gws' binary was not found"):
            _binary.resolve()


def test_resolve_sets_executable_bit(tmp_path):
    fake = tmp_path / "gws"
    fake.write_text("#!/bin/sh\n")
    os.chmod(fake, 0o600)
    with patch.object(_binary, "_bundled_path", return_value=str(fake)):
        with patch.object(_binary.sys, "platform", "linux"):
            resolved = _binary.resolve()
    assert resolved == str(fake)
    assert os.stat(fake).st_mode & stat.S_IXUSR


@pytest.mark.parametrize(
    "system,machine,expected",
    [
        ("Linux", "x86_64", "linux-x86_64"),
        ("Linux", "aarch64", "linux-aarch64"),
        ("Darwin", "arm64", "macos-arm64"),
        ("Darwin", "x86_64", "macos-x86_64"),
        ("Windows", "AMD64", "windows-amd64"),
    ],
)
def test_arch_tag(system, machine, expected):
    with patch.object(_binary.platform, "system", return_value=system):
        with patch.object(_binary.platform, "machine", return_value=machine):
            assert _binary.arch_tag() == expected


def test_version_parses_output():
    proc = MagicMock(stdout="gws 0.22.5\nThis is not official\n", stderr="", returncode=0)
    with patch.object(subprocess, "run", return_value=proc):
        assert _binary.version(path="/x/gws") == "0.22.5"


def test_is_available_true_false(tmp_path):
    fake = tmp_path / "gws"
    fake.write_text("x")
    with patch.object(_binary, "_bundled_path", return_value=str(fake)):
        assert _binary.is_available() is True
    with patch.object(_binary, "_bundled_path", return_value=str(tmp_path / "no")):
        assert _binary.is_available() is False
