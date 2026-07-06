# Changelog

The changelog format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

**Versioning:** releases use a four-segment version, `<gws-version>.<ext-release>` (e.g.
`0.22.6.1`, `0.22.6.2`). The first three segments mirror the bundled
[`gws`](https://github.com/googleworkspace/cli) CLI version; the fourth is this extension's
own release counter, so one `gws` release maps to many extension releases.

This is valid [PEP 440](https://peps.python.org/pep-0440/) (installable from PyPI) but is
**not** [SemVer](https://semver.org/), which requires exactly three `MAJOR.MINOR.PATCH`
segments. (A SemVer build tag like `0.22.6+1` is a PEP 440 local version that PyPI rejects,
so the coupled four-segment scheme is used instead.)

```{towncrier-draft-entries}
```

```{include} ../CHANGELOG.md
:start-after: '# Changelog'
```
