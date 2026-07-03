"""
Single choke point through which every generated module invokes the ``gws`` CLI.

Responsibilities:

* build the ``gws <service> <resource...> <method>`` argv (never putting secrets on it),
* inject pillar-derived credentials into the environment (see :mod:`saltext.gsuite._auth`),
* run the subprocess and translate its JSON output / exit code into a Python value or a
  :class:`salt.exceptions.CommandExecutionError`.
"""

import json
import logging
import subprocess

from saltext.gsuite import _auth
from saltext.gsuite import _binary

try:
    from salt.exceptions import CommandExecutionError
except ImportError:  # pragma: no cover - allows importing outside a salt runtime

    class CommandExecutionError(Exception):
        """Fallback used when Salt is not importable."""


log = logging.getLogger(__name__)

# gws exit codes (see the CLI's error module).
EXIT_OK = 0
EXIT_API = 1
EXIT_AUTH = 2
EXIT_VALIDATION = 3
EXIT_DISCOVERY = 4
EXIT_INTERNAL = 5

_EXIT_LABEL = {
    EXIT_API: "API error",
    EXIT_AUTH: "authentication error",
    EXIT_VALIDATION: "validation error",
    EXIT_DISCOVERY: "discovery error",
    EXIT_INTERNAL: "internal gws error",
}

# Reserved control kwargs pulled out of a call's params so generated function signatures can
# stay a clean ``(**params)`` while still exposing these knobs uniformly.
_RESERVED = ("test", "page_all", "page_limit", "page_delay", "output", "timeout")


def _build_argv(path, service, resource_path, method):
    argv = [path, service]
    argv.extend(resource_path)
    argv.append(method)
    return argv


def _parse(proc, page_all):
    """Turn a completed subprocess into a Python value or raise CommandExecutionError."""
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""

    if proc.returncode != EXIT_OK:
        error = _extract_error(stdout)
        if error:
            code = error.get("code")
            reason = error.get("reason")
            message = error.get("message", "")
            detail = f"gws {_EXIT_LABEL.get(proc.returncode, 'error')}"
            if reason:
                detail += f" [{reason}]"
            if code:
                detail += f" (code {code})"
            raise CommandExecutionError(f"{detail}: {message}".strip())
        raise CommandExecutionError(
            f"gws exited with code {proc.returncode}: {(stderr or stdout).strip()}"
        )

    if page_all:
        pages = []
        for line in stdout.splitlines():
            line = line.strip()
            if line:
                pages.append(json.loads(line))
        return pages

    stripped = stdout.strip()
    if not stripped:
        return {}
    data = json.loads(stripped)
    # A zero exit with an embedded error object should still surface as an error.
    if isinstance(data, dict) and "error" in data and isinstance(data["error"], dict):
        err = data["error"]
        raise CommandExecutionError(
            f"gws error [{err.get('reason')}] (code {err.get('code')}): {err.get('message', '')}"
        )
    return data


def _extract_error(stdout):
    try:
        data = json.loads(stdout.strip()) if stdout.strip() else None
    except ValueError:
        return None
    if isinstance(data, dict) and isinstance(data.get("error"), dict):
        return data["error"]
    return None


def _split_reserved(params, opts):
    """Separate reserved control kwargs from real API params."""
    params = dict(params or {})
    control = {}
    for key in _RESERVED:
        if key in params:
            control[key] = params.pop(key)
    if "test" not in control:
        control["test"] = bool((opts or {}).get("test", False))
    return params, control


def call(
    opts,
    pillar,
    service,
    resource_path,
    method,
    *,
    params=None,
    body=None,
    upload=None,
):
    """
    Invoke a single ``gws`` method.

    ``resource_path`` is the list of resource/sub-resource command segments (e.g.
    ``["users", "messages"]`` for ``gmail users messages``). Reserved control keys
    (``test``, ``page_all``, ``page_limit``, ``page_delay``, ``output``, ``timeout``) may be
    passed inside ``params`` and are extracted automatically.
    """
    api_params, control = _split_reserved(params, opts)
    return run(
        service,
        resource_path,
        method,
        params=api_params or None,
        body=body,
        upload=upload,
        output=control.get("output"),
        page_all=bool(control.get("page_all", False)),
        page_limit=control.get("page_limit"),
        page_delay=control.get("page_delay"),
        test=bool(control.get("test", False)),
        timeout=control.get("timeout", 120),
        opts=opts,
        pillar=pillar,
    )


def run(
    service,
    resource_path,
    method,
    *,
    params=None,
    body=None,
    upload=None,
    output=None,
    page_all=False,
    page_limit=None,
    page_delay=None,
    test=False,
    timeout=120,
    opts=None,
    pillar=None,
):
    """Low-level runner. Returns parsed JSON (dict/list) or raises CommandExecutionError."""
    path = _binary.resolve(opts=opts, pillar=pillar)
    argv = _build_argv(path, service, list(resource_path), method)
    argv += ["--format", "json"]
    if params:
        argv += ["--params", json.dumps(params, sort_keys=True)]
    if body is not None:
        argv += ["--json", json.dumps(body, sort_keys=True)]
    if upload:
        argv += ["--upload", upload]
    if output:
        argv += ["--output", output]
    if page_all:
        argv += ["--page-all"]
        if page_limit is not None:
            argv += ["--page-limit", str(page_limit)]
        if page_delay is not None:
            argv += ["--page-delay", str(page_delay)]
    if test:
        argv += ["--dry-run"]

    log.debug("Invoking gws: %s", " ".join(argv[1:]))  # argv[0] is the binary path
    try:
        with _auth.environment(pillar=pillar, opts=opts) as env:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                env=env,
                timeout=timeout,
                check=False,
            )
    except _auth.AuthError as exc:
        raise CommandExecutionError(f"gsuite auth configuration error: {exc}") from exc
    except _binary.BinaryError as exc:
        raise CommandExecutionError(str(exc)) from exc
    except subprocess.TimeoutExpired as exc:
        raise CommandExecutionError(
            f"gws call timed out after {timeout}s: {service} {' '.join(resource_path)} {method}"
        ) from exc
    except OSError as exc:
        raise CommandExecutionError(f"Failed to execute gws: {exc}") from exc

    return _parse(proc, page_all)


def run_helper(
    opts,
    pillar,
    service,
    command,
    *,
    positionals=None,
    flags=None,
    switches=None,
    test=False,
    timeout=120,
):
    """
    Invoke a curated ``+helper`` command (e.g. ``gws drive +upload <file> --parent X``).

    ``positionals`` are appended in order; ``flags`` is a mapping of ``long -> value`` where a
    list value is repeated (``-a a -a b``) and None values are dropped; ``switches`` is a
    mapping of ``long -> bool`` rendered as bare ``--long`` when true.
    """
    path = _binary.resolve(opts=opts, pillar=pillar)
    argv = [path, service, command]
    for value in positionals or []:
        if value is not None:
            argv.append(str(value))
    for long, value in (flags or {}).items():
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            for item in value:
                argv += [f"--{long}", str(item)]
        else:
            argv += [f"--{long}", str(value)]
    for long, value in (switches or {}).items():
        if value:
            argv.append(f"--{long}")
    argv += ["--format", "json"]
    if test:
        argv += ["--dry-run"]

    log.debug("Invoking gws helper: %s", " ".join(argv[1:]))
    try:
        with _auth.environment(pillar=pillar, opts=opts) as env:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                env=env,
                timeout=timeout,
                check=False,
            )
    except _auth.AuthError as exc:
        raise CommandExecutionError(f"gsuite auth configuration error: {exc}") from exc
    except _binary.BinaryError as exc:
        raise CommandExecutionError(str(exc)) from exc
    except subprocess.TimeoutExpired as exc:
        raise CommandExecutionError(
            f"gws helper timed out after {timeout}s: {service} {command}"
        ) from exc
    except OSError as exc:
        raise CommandExecutionError(f"Failed to execute gws: {exc}") from exc

    return _parse(proc, False)
