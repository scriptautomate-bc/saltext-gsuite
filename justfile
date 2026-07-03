# saltext-gsuite developer commands.
#
# Unit tests are hermetic (mocked subprocess, no network, no gws binary needed). We disable the
# pytest-salt-factories daemon sub-plugins (event listener / log server / factories) for unit
# runs: they bind sockets at session start and are unnecessary for mocked tests (and hang in
# some sandboxed/container environments). The loader-mock sub-plugin that powers
# `configure_loader_modules` stays enabled. Integration tests re-enable everything.

python := env_var_or_default("PYTHON", ".venv/bin/python")

# pytest-salt-factories sub-plugins that are irrelevant to hermetic unit tests.
no_daemons := "-p no:salt-factories -p no:salt-factories-event-listener -p no:salt-factories-log-server -p no:salt-factories-factories -p no:salt-factories-sysinfo -p no:system-statistics"

# List recipes.
default:
    @just --list

# Create/refresh the dev virtualenv with all extras.
sync:
    uv pip install --python {{python}} -e ".[tests,lint,docs]" jinja2 black==26.5.1 isort==8.0.1

# Run the hermetic unit test suite.
test *args:
    {{python}} -m pytest tests/unit {{no_daemons}} -p no:cacheprovider {{args}}

# Run the opt-in integration suite (requires real service-account creds via pillar/env).
test-integration *args:
    GSUITE_INTEGRATION_TESTS=1 {{python}} -m pytest tests/integration {{args}}

# Lint generated + hand-written code with pylint via nox.
lint:
    {{python}} -m nox -e lint

# Regenerate the entire module surface from Discovery + the bundled gws CLI.
generate *args:
    {{python}} tools/generate_modules.py --all {{args}}

# Verify the generator is deterministic (re-run must produce no diff).
check-determinism:
    {{python}} tools/generate_modules.py --all
    git diff --exit-code -- src/saltext/gsuite/modules src/saltext/gsuite/states src/saltext/gsuite/metadata/schemas tests/unit docs/ref

# Bump the bundled gws version and regenerate (see tools/update_gws.py).
update-gws version:
    {{python}} tools/update_gws.py {{version}}

# Build the docs.
docs:
    {{python}} -m nox -e docs

# Format all Python with isort + black.
fmt:
    {{python}} -m isort src tests tools
    {{python}} -m black src tests tools
