from unittest.mock import patch

import pytest

from saltext.gsuite.modules import gsuite_util


@pytest.fixture
def configure_loader_modules():
    return {
        gsuite_util: {
            "__opts__": {"test": False},
            "__pillar__": {},
        }
    }


def test_virtual():
    assert gsuite_util.__virtual__() == "gsuite"


def test_version_success():
    with patch.object(gsuite_util._binary, "version", return_value="0.22.5"):
        with patch.object(gsuite_util._binary, "resolve", return_value="/x/gws"):
            ret = gsuite_util.version()
    assert ret["gws"] == "0.22.5"
    assert ret["binary"] == "/x/gws"
    assert "extension" in ret


def test_version_missing_binary():
    err = gsuite_util._binary.BinaryError("nope")
    with patch.object(gsuite_util._binary, "version", side_effect=err):
        ret = gsuite_util.version()
    assert ret["gws"] is None
    assert "nope" in ret["error"]


def test_call_simple_resource():
    with patch.object(gsuite_util._gws, "call", return_value={"ok": True}) as call:
        ret = gsuite_util.call("drive", "files", "list", params={"pageSize": 5})
    assert ret == {"ok": True}
    args = call.call_args.args
    assert args[2] == "drive"
    assert args[3] == ["files"]
    assert args[4] == "list"


def test_call_nested_subresource():
    with patch.object(gsuite_util._gws, "call", return_value={}) as call:
        gsuite_util.call("gmail", "users", "list", subresource="messages")
    assert call.call_args.args[3] == ["users", "messages"]


def test_auth_test_success():
    with patch.object(gsuite_util._gws, "call", return_value={"user": {"emailAddress": "a@b"}}):
        ret = gsuite_util.auth_test()
    assert ret["result"] is True
    assert ret["about"]["user"]["emailAddress"] == "a@b"


def test_auth_test_failure():
    err = gsuite_util._gws.CommandExecutionError("bad creds")
    with patch.object(gsuite_util._gws, "call", side_effect=err):
        ret = gsuite_util.auth_test()
    assert ret["result"] is False
    assert "bad creds" in ret["error"]
