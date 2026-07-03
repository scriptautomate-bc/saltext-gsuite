"""
Resolve the ``gws`` (Google Workspace CLI) binary bundled inside the installed wheel.

The binary is shipped as package data at ``saltext/gsuite/_vendor/gws`` (``gws.exe`` on
Windows). Each extension wheel is platform specific and carries the matching binary, so no
download happens at runtime. A pillar/opts override (``gsuite:binary_path``) may point at an
externally managed copy, which then wins over the bundled one.
"""

import logging
import os
import platform
import stat
import subprocess
import sys
from importlib.resources import files as _resource_files

log = logging.getLogger(__name__)

PACKAGE = "saltext.gsuite"
VENDOR_DIRNAME = "_vendor"


class BinaryError(Exception):
    """Raised when the bundled ``gws`` binary cannot be located or used."""


def binary_name():
    """Return the platform-specific file name of the ``gws`` binary."""
    return "gws.exe" if sys.platform.startswith("win") else "gws"


def arch_tag():
    """
    Return the ``<os>-<arch>`` key describing the current platform.

    Matches the keys used in ``metadata/gws_release.json`` so error messages can point the
    user at the correct platform wheel.
    """
    system = platform.system().lower()
    machine = platform.machine().lower()
    os_key = {"linux": "linux", "darwin": "macos", "windows": "windows"}.get(system, system)
    arch_key = {
        "x86_64": "x86_64",
        "amd64": "x86_64" if os_key != "windows" else "amd64",
        "aarch64": "aarch64",
        "arm64": "arm64",
    }.get(machine, machine)
    if os_key == "windows":
        arch_key = "amd64"
    elif os_key == "macos" and arch_key == "x86_64":
        arch_key = "x86_64"
    elif os_key == "macos" and arch_key in ("aarch64", "arm64"):
        arch_key = "arm64"
    return f"{os_key}-{arch_key}"


def _bundled_path():
    """Absolute path to where the bundled binary should live inside the package."""
    name = binary_name()
    try:
        root = _resource_files(PACKAGE)
        candidate = os.path.join(str(root), VENDOR_DIRNAME, name)
        if os.path.exists(candidate):
            return candidate
    except Exception:  # pylint: disable=broad-except
        pass
    # Fallback: relative to this file (editable installs, unusual loaders).
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), VENDOR_DIRNAME, name)


def _dig(mapping, *keys):
    """Safely walk nested dict-likes, returning None on any missing/None level."""
    cur = mapping
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
        if cur is None:
            return None
    return cur


def override_path(opts=None, pillar=None):
    """Return an explicit ``gsuite:binary_path`` override from opts or pillar, if any."""
    for source in (opts, pillar):
        value = _dig(source, "gsuite", "binary_path")
        if value:
            return value
    return None


def _ensure_executable(path):
    """On POSIX, make sure the file carries the owner/group/other execute bits."""
    if sys.platform.startswith("win"):
        return
    try:
        mode = os.stat(path).st_mode
        want = mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
        if want != mode:
            os.chmod(path, want)
    except OSError as exc:  # pragma: no cover - best effort
        log.debug("Could not set executable bit on %s: %s", path, exc)


def resolve(opts=None, pillar=None):
    """
    Return the absolute path to a usable ``gws`` binary.

    An explicit ``gsuite:binary_path`` override wins if present; otherwise the binary bundled
    in the wheel is used. Raises :class:`BinaryError` with an actionable message if none is
    available.
    """
    override = override_path(opts, pillar)
    if override:
        if os.path.isfile(override):
            _ensure_executable(override)
            return override
        raise BinaryError(
            f"gsuite:binary_path is set to '{override}', but no file exists at that path."
        )

    path = _bundled_path()
    if not os.path.isfile(path):
        raise BinaryError(
            "The bundled 'gws' binary was not found at "
            f"'{path}' (platform '{arch_tag()}'). This usually means the package was installed "
            "from an sdist or a wheel built for a different platform. Install the platform "
            "specific wheel for this architecture, or set 'gsuite:binary_path' to an external "
            "gws binary."
        )
    _ensure_executable(path)
    return path


def version(path=None, opts=None, pillar=None):
    """Return the version string reported by ``gws --version`` (e.g. ``0.22.5``)."""
    if path is None:
        path = resolve(opts=opts, pillar=pillar)
    try:
        proc = subprocess.run(
            [path, "--version"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise BinaryError(f"Failed to execute '{path} --version': {exc}") from exc
    first = (proc.stdout or proc.stderr or "").strip().splitlines()
    if not first:
        raise BinaryError(f"'{path} --version' produced no output")
    # Output looks like: "gws 0.22.5"
    parts = first[0].split()
    return parts[-1] if parts else first[0]


def is_available(opts=None, pillar=None):
    """Return True if a ``gws`` binary can be resolved, without raising."""
    try:
        resolve(opts=opts, pillar=pillar)
        return True
    except BinaryError:
        return False
