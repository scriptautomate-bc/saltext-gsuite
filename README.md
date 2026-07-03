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

### Regenerating the surface

The entire module/state/test/doc surface is generated and committed. To absorb a new `gws`
release, bump the pin and re-run the reconciler (creates/updates/deletes to match exactly what
the CLI exposes):

```bash
just update-gws 0.22.6   # bump + refresh SHAs + regenerate
just generate            # regenerate against the current pin
just test                # hermetic unit suite (mocked, no network/binary)
```

Versioning couples the extension to the bundled CLI: the version is `<gws-version>.<ext-release>`
(e.g. gws `0.22.5` → first extension release `v0.22.5.1`).

## Security

If you discover a security vulnerability, please refer
to [Salt's security guide][security].

## User Documentation

For setup and usage instructions, please refer to the
[User Documentation][docs].

## Contributing

The saltext-gsuite project welcomes contributions from anyone!

The [Salt Extensions guide][salt-extensions-guide] provides comprehensive instructions on all aspects
of Salt extension development, including [writing tests][writing-tests], [running tests][running-tests],
[writing documentation][writing-docs] and [rendering the docs][rendering-docs].

### Quickstart

To get started contributing, first clone this repository (or your fork):

```bash
# Clone the repo
git clone --origin upstream git@github.com:salt-extensions/saltext-gsuite.git

# Change to the repo dir
cd saltext-gsuite
```

#### Automatic
If you have installed [direnv][direnv], copying the included `.envrc.example` to `.envrc` and
allowing it to run ensures a proper development environment is present and the virtual environment is active.

Without `direnv`, you can still run the automation explicitly:

```bash
make dev  # or python3 tools/initialize.py
source .venv/bin/activate
```

#### Manual
Please follow the [first steps][first-steps], skipping the repository initialization and first commit.

### Pull request

Always make changes in a feature branch:

```bash
git switch -c my-feature-branch
```

Please ensure you include a [news fragment](https://salt-extensions.github.io/salt-extension-copier/topics/documenting/changelog.html#procedure)
describing your changes. This is a requirement for all user-facing changes (bug fixes, new features),
with the exception of documentation changes.

To [submit a Pull Request][submitting-pr], you'll need a fork of this repository in
your own GitHub account. If you followed the instructions above,
set your fork as the `origin` remote now:

```bash
git remote add origin git@github.com:<your_fork>.git
```

Ensure you followed the [first steps][first-steps] and commit your changes, fixing any
failing `pre-commit` hooks. Then push the feature branch to your fork and submit a PR.

### Ways to contribute

Contributions come in many forms, and they’re all valuable! Here are some ways you can help
without writing code:

* **Documentation**: Especially examples showing how to use this project
  to solve specific problems.
* **Triaging issues**: Help manage [issues][issues] and participate in [discussions][discussions].
* **Reviewing [Pull Requests][PRs]**: We especially appreciate reviews using [Conventional Comments][comments].

You can also contribute by:

* Writing blog posts
* Sharing your experiences using Salt + Google Workspace Suite
  on social media
* Giving talks at conferences
* Publishing videos
* Engaging in IRC, Discord or email groups

Any of these things are super valuable to our community, and we sincerely
appreciate every contribution!

[security]: https://github.com/saltstack/salt/blob/master/SECURITY.md
[salt-extensions-guide]: https://salt-extensions.github.io/salt-extension-copier/
[writing-tests]: https://salt-extensions.github.io/salt-extension-copier/topics/testing/writing.html
[running-tests]: https://salt-extensions.github.io/salt-extension-copier/topics/testing/running.html
[writing-docs]: https://salt-extensions.github.io/salt-extension-copier/topics/documenting/writing.html
[rendering-docs]: https://salt-extensions.github.io/salt-extension-copier/topics/documenting/building.html
[first-steps]: https://salt-extensions.github.io/salt-extension-copier/topics/creation.html#initialize-the-python-virtual-environment
[submitting-pr]: https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/creating-a-pull-request-from-a-fork
[direnv]: https://direnv.net
[issues]: https://github.com/salt-extensions/saltext-gsuite/issues
[PRs]: https://github.com/salt-extensions/saltext-gsuite/pulls
[discussions]: https://github.com/salt-extensions/saltext-gsuite/discussions
[comments]: https://conventionalcomments.org/
[docs]: https://salt-extensions.github.io/saltext-gsuite/
