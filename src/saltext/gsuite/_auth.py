"""
Translate Salt pillar credentials into the environment variables the ``gws`` CLI understands.

Secrets are only ever passed through the process environment (never on argv, so they cannot
leak via ``ps``/``/proc``), and inline service-account JSON is staged into a ``0600`` temp file
that is removed as soon as the call finishes.

Supported pillar schema::

    gsuite:
      auth:
        method: service_account | token | credentials_file | adc
        service_account: { ... full service account JSON ... }
        token: "ya29..."
        credentials_file: /etc/gws/creds.json
        subject: user@domain.com          # reserved; see note below
        project_id: my-gcp-project
      config_dir: /var/cache/salt/.../gsuite/gws-home
      binary_path: null

.. note::
    Domain-wide delegation (``subject``) has no environment mapping in the bundled ``gws``
    release, so it is accepted but ignored with a warning. It is retained in the schema for
    forward compatibility.
"""

import contextlib
import json
import logging
import os
import stat
import tempfile

log = logging.getLogger(__name__)

ENV_TOKEN = "GOOGLE_WORKSPACE_CLI_TOKEN"
ENV_CREDENTIALS_FILE = "GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE"
ENV_CONFIG_DIR = "GOOGLE_WORKSPACE_CLI_CONFIG_DIR"
ENV_KEYRING_BACKEND = "GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND"
ENV_PROJECT_ID = "GOOGLE_WORKSPACE_PROJECT_ID"
ENV_ADC = "GOOGLE_APPLICATION_CREDENTIALS"

# Env vars this module manages. Any pre-existing values are cleared before we apply our own
# so that a minion's ambient environment can never silently override pillar-driven auth.
_MANAGED = (ENV_TOKEN, ENV_CREDENTIALS_FILE, ENV_ADC)


class AuthError(Exception):
    """Raised when pillar credential configuration is invalid."""


def _dig(mapping, *keys, default=None):
    cur = mapping
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
        if cur is None:
            return default
    return cur


def _config_dir(pillar, opts):
    """Resolve the isolated GWS config/state dir, defaulting under the minion cachedir."""
    explicit = _dig(pillar, "gsuite", "config_dir")
    if explicit:
        return explicit
    cachedir = _dig(opts, "cachedir")
    if cachedir:
        return os.path.join(cachedir, "gsuite", "gws-home")
    return os.path.join(tempfile.gettempdir(), "saltext-gsuite", "gws-home")


@contextlib.contextmanager
def environment(pillar=None, opts=None, base_env=None):
    """
    Context manager yielding an environment dict with credentials wired up for ``gws``.

    Any temporary secret files created for inline service-account JSON are removed on exit.
    """
    env = dict(os.environ if base_env is None else base_env)
    for name in _MANAGED:
        env.pop(name, None)

    auth = _dig(pillar, "gsuite", "auth", default={}) or {}
    if not isinstance(auth, dict):
        raise AuthError("gsuite:auth must be a mapping")

    config_dir = _config_dir(pillar, opts)
    try:
        os.makedirs(config_dir, mode=0o700, exist_ok=True)
    except OSError as exc:  # pragma: no cover - filesystem dependent
        log.debug("Could not create gws config dir %s: %s", config_dir, exc)
    env[ENV_CONFIG_DIR] = config_dir
    # Headless minions have no OS keyring; force the file backend.
    env.setdefault(ENV_KEYRING_BACKEND, "file")
    env[ENV_KEYRING_BACKEND] = "file"

    project_id = auth.get("project_id")
    if project_id:
        env[ENV_PROJECT_ID] = str(project_id)

    if auth.get("subject"):
        log.warning(
            "gsuite:auth:subject (domain-wide delegation) is set but the bundled gws release "
            "has no environment mapping for it; the value is ignored."
        )

    method = auth.get("method")
    token = auth.get("token")
    credentials_file = auth.get("credentials_file")
    service_account = auth.get("service_account")

    # Infer the method when not given explicitly.
    if not method:
        if token:
            method = "token"
        elif service_account:
            method = "service_account"
        elif credentials_file:
            method = "credentials_file"
        else:
            method = "adc"

    tmp_path = None
    try:
        if method == "token":
            if not token:
                raise AuthError("gsuite:auth:method is 'token' but no 'token' was provided")
            env[ENV_TOKEN] = str(token)
        elif method == "credentials_file":
            if not credentials_file:
                raise AuthError(
                    "gsuite:auth:method is 'credentials_file' but no 'credentials_file' path "
                    "was provided"
                )
            if not os.path.isfile(credentials_file):
                raise AuthError(
                    f"gsuite:auth:credentials_file '{credentials_file}' does not exist"
                )
            env[ENV_CREDENTIALS_FILE] = str(credentials_file)
        elif method == "service_account":
            if not service_account:
                raise AuthError(
                    "gsuite:auth:method is 'service_account' but no 'service_account' JSON was "
                    "provided"
                )
            tmp_path = _stage_secret(service_account, config_dir)
            env[ENV_CREDENTIALS_FILE] = tmp_path
        elif method == "adc":
            # Rely on ambient GOOGLE_APPLICATION_CREDENTIALS / metadata server. If pillar
            # supplied an explicit path, honour it.
            adc_path = auth.get("application_credentials") or _dig(pillar, "gsuite", "auth", "adc")
            if isinstance(adc_path, str):
                env[ENV_ADC] = adc_path
        else:
            raise AuthError(f"Unknown gsuite:auth:method '{method}'")

        yield env
    finally:
        if tmp_path:
            with contextlib.suppress(OSError):
                os.remove(tmp_path)


def _stage_secret(service_account, config_dir):
    """Write inline service-account JSON to a private temp file, returning its path."""
    if isinstance(service_account, str):
        payload = service_account
    else:
        payload = json.dumps(service_account)
    fd, path = tempfile.mkstemp(prefix="gsuite-sa-", suffix=".json", dir=config_dir)
    try:
        os.fchmod(fd, stat.S_IRUSR | stat.S_IWUSR)  # 0600
        with os.fdopen(fd, "w") as handle:
            handle.write(payload)
    except Exception:
        with contextlib.suppress(OSError):
            os.remove(path)
        raise
    return path
