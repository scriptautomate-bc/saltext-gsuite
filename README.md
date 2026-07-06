# Salt Extension for Google Workspace Suite

Salt Extension for interacting with all of Google Workspace.

## Overview

`saltext.gsuite` provides native `gsuite_<service>.*` execution and state modules for the
**entire** Google Workspace API surface — 18 services (drive, gmail, calendar, sheets, docs,
slides, tasks, people, chat, classroom, forms, keep, meet, admin-reports, events, modelarmor,
workflow, script), ~470 methods.

Rather than reimplement Google's API clients in Python, the extension drives the official
[`gws` CLI](https://github.com/googleworkspace/cli) as a subprocess and **auto-generates** the
whole Python surface from Google's Discovery API. The pinned `gws` binary is **bundled inside
per-architecture wheels**, so a single `pip install` works fully offline — no runtime download.

```bash
salt '*' gsuite.version                              # extension + bundled gws version
salt '*' gsuite.auth_test                            # validate pillar credentials
salt '*' gsuite_drive.files_list pageSize=5          # real API call
salt '*' gsuite_drive.files_list pageSize=5 test=True # --dry-run, no API call
salt '*' gsuite_gmail.users_messages_list userId=me
```

Credentials flow from Salt pillar into `gws`'s environment-variable credential model — see the
[configuration docs](docs/topics/configuration.md). Function names and parameters mirror the
Google API reference verbatim (e.g. `files_list`, `users_messages_send`, `fileId`, `pageSize`).

## Security

If you discover a security vulnerability, please refer
to [Salt's security guide][security].

## User Documentation

For setup and usage instructions, please refer to the
[User Documentation][docs].

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup,
regenerating the code surface, testing, and the pull request process. Maintainer release
procedures are documented in [RELEASE.md](RELEASE.md).

[security]: https://github.com/saltstack/salt/blob/master/SECURITY.md
[docs]: https://salt-extensions.github.io/saltext-gsuite/
