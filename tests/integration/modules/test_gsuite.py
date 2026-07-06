"""
Opt-in integration smoke tests against the real Google Workspace API.

These are skipped unless ``GSUITE_INTEGRATION_TESTS=1`` is set and real service-account
credentials are available to the minion (via pillar or the gws credential env vars). They make
a handful of read-only calls plus one create/delete round-trip on a scratch Drive file.

Run with::

    just test-integration
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("GSUITE_INTEGRATION_TESTS") != "1",
    reason="set GSUITE_INTEGRATION_TESTS=1 and provide real credentials to run",
)


@pytest.fixture
def modules(loaders):
    return loaders.modules


def test_version(modules):
    ret = modules.gsuite.version()
    assert ret["gws"]
    assert ret["extension"]


def test_auth_test(modules):
    ret = modules.gsuite.auth_test()
    assert ret["result"] is True, ret


def test_drive_files_list(modules):
    ret = modules.gsuite_drive.files_list(pageSize=5)
    assert "files" in ret


def test_drive_file_roundtrip(modules):
    created = modules.gsuite_drive.files_create(body={"name": "saltext-gsuite-integration-scratch"})
    file_id = created["id"]
    try:
        fetched = modules.gsuite_drive.files_get(file_id)
        assert fetched["id"] == file_id
    finally:
        modules.gsuite_drive.files_delete(file_id)
