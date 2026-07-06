# Release process

This document covers the maintainer-facing release workflow: versioning, changelog generation,
tagging, and publishing to PyPI. For development setup and the day-to-day contribution workflow,
see [CONTRIBUTING.md](CONTRIBUTING.md).

## Versioning

The package version is dynamic, derived from git tags via `setuptools_scm`
(`[tool.setuptools_scm]` in `pyproject.toml`, written to `src/saltext/gsuite/version.py`).

Release tags follow a 4-segment scheme that couples the extension to its bundled `gws` CLI
version:

```
v<gws-major>.<gws-minor>.<gws-patch>.<ext-release>
```

For example, gws `0.22.5` → first extension release `v0.22.5.1`. Bumping to a new pinned `gws`
version resets `<ext-release>` to `1`; an extension-only change against the same `gws` version
increments `<ext-release>`. `tools/update_gws.py --check-tag` enforces that a pushed tag matches
the currently pinned `gws` version — see [Bumping the `gws` binary](CONTRIBUTING.md#bumping-the-bundled-gws-version)
in CONTRIBUTING.md for how the pin itself is bumped.

## Changelog (towncrier)

Changelog entries are managed with [towncrier][towncrier] (`[tool.towncrier]` in
`pyproject.toml`), rendering into `CHANGELOG.md` from fragment files in `changelog/`.

Each user-facing change should add a fragment named `<id>.<type>.md`, where `<type>` is one of:

| type         | meaning                    |
|--------------|-----------------------------|
| `breaking`   | Breaking changes            |
| `removed`    | Removed                     |
| `deprecated` | Deprecated                  |
| `changed`    | Changed                     |
| `fixed`      | Fixed                       |
| `added`      | Added                       |
| `security`   | Security                    |

`tools/version.py` derives the next semantic version from whichever fragment types are present
in `changelog/` at release time:

- Any `.breaking.md`/`.removed.md` fragment, or `.added.md` content matching `BREAKING:` → **major**
  bump.
- Any `.added.md` fragment (no breaking marker) → **minor** bump.
- Otherwise (only `fixed`/`changed`/`deprecated`/`security`) → **patch** bump.

Run `python tools/version.py next` to see what the next version would be given the current
fragments.

## Automated release flow

Releases are driven end-to-end by GitHub Actions; there is normally no manual tagging step.

1. **`prepare-release-action.yml`** (workflow, only runs on the default branch) computes the next
   version via `tools/version.py next`, runs `towncrier build --yes --version <version>` to
   render `CHANGELOG.md` from the pending fragments, and opens/updates a PR from branch
   `release/auto` labeled `release`, titled `Release v<version>`.
2. Merging that PR into the default branch triggers **`tag-auto.yml`**, which re-validates the PR
   (correct source branch/label, title matches the version, no leftover changelog fragments),
   then creates and pushes the annotated tag `v<version>`.
3. The tag push triggers the central **`ci.yml`** workflow (also reachable directly via
   **`tag.yml`** if a `v*` tag is pushed manually — it performs the same fragment/version
   validation as `tag-auto.yml` and closes any stale auto-release PR).
4. **`deploy-package-action.yml`** runs on `workflow_run` after `ci.yml` completes for either
   trigger: it verifies the built wheel's version, publishes to Test PyPI then to PyPI (trusted
   publishing via OIDC), triggers the docs deploy, and creates the GitHub Release with generated
   notes and dist artifacts attached.
5. **`release-wheels.yml`**, triggered by the 4-segment tag pattern `v*.*.*.*`, first checks the
   tag matches the currently pinned `gws` version (`tools/update_gws.py --check-tag`), then builds
   one wheel per supported platform/arch (linux x86_64/aarch64, macOS x86_64/arm64, windows
   amd64), bundling the fetched `gws` binary via `tools/fetch_binary.py`, plus a source-only
   sdist, and publishes all of them to PyPI via trusted publishing.

## Bumping the `gws` binary ahead of a release

The pinned `gws` version determines the first three segments of the next release tag, so it must
be bumped *before* cutting a release for a new `gws` version:

```bash
just update-gws <new-gws-version>
```

This is described from the day-to-day development angle in
[CONTRIBUTING.md](CONTRIBUTING.md#bumping-the-bundled-gws-version). In practice this step is
usually already done for you: **`gws-autoupdate.yml`** runs daily, detects new
`googleworkspace/cli` releases, and opens a PR (branch `gws-bump/<version>`) with the bump,
regenerated surface, a passing `just test` run, and a changelog fragment
(`changelog/gws-<version>.changed.md`) already included. Merge that PR before/along with the
next release PR from step 1 above.

## Manual / emergency releases

- To force a specific version instead of the auto-computed one, dispatch
  `prepare-release-action.yml` manually and supply a version override.
- To bypass the automated PR flow entirely (e.g. the `release/auto` PR is stuck), you can push an
  annotated tag directly: `git tag -a v<version> -m "Release v<version>" && git push origin
  v<version>`. `tag.yml` runs the same fragment/version validation as the automated path before
  handing off to `ci.yml`, so the changelog must already be rendered and fragments cleared before
  pushing the tag.

[towncrier]: https://towncrier.readthedocs.io/
