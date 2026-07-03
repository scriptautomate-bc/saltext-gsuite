# Configuration

`saltext.gsuite` drives the bundled [`gws`](https://github.com/googleworkspace/cli) CLI as a
subprocess. Credentials flow from Salt pillar into the environment variables `gws` understands;
secrets are only ever passed through the environment (never on the command line) and inline
service-account JSON is staged into a `0600` temporary file that is removed after each call.

## Pillar schema

```yaml
gsuite:
  auth:
    # One of: service_account | token | credentials_file | adc
    # (inferred from which key you set if omitted)
    method: service_account

    # Inline service-account JSON (e.g. from GPG/vault pillar). Written to a private
    # temp file for the duration of each call.
    service_account:
      type: service_account
      project_id: my-gcp-project
      private_key_id: "..."
      private_key: "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
      client_email: my-sa@my-gcp-project.iam.gserviceaccount.com
      # ...

    # OR a pre-obtained OAuth2 access token:
    # token: "ya29...."

    # OR a credentials file already present on the minion:
    # credentials_file: /etc/gws/creds.json

    # OR application default credentials:
    # method: adc
    # application_credentials: /etc/gws/adc.json   # optional explicit path

    project_id: my-gcp-project     # optional quota/billing project (GOOGLE_WORKSPACE_PROJECT_ID)
    subject: user@example.com      # reserved; not supported by the bundled gws release yet

  # Isolated per-minion gws state directory (defaults under the minion cachedir).
  config_dir: /var/cache/salt/minion/gsuite/gws-home

  # Optional: use an externally managed gws binary instead of the bundled one.
  binary_path: null
```

## Verifying credentials

```bash
salt '*' gsuite.version      # reports the extension version + bundled gws version
salt '*' gsuite.auth_test    # runs an authenticated `drive about get`
```

## Test mode

Every execution function accepts `test=True`, which maps to `gws --dry-run`: the request is
validated locally and the URL/params that *would* be sent are returned, without calling the
Google API. State modules honour `test=True` from `__opts__` the same way.

```bash
salt '*' gsuite_drive.files_list pageSize=5 test=True
```
