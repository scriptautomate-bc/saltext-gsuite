from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from saltext.gsuite import _gws


@pytest.fixture(autouse=True)
def _stub_binary_and_auth(tmp_path):
    """Avoid touching the real binary/auth; capture argv and env instead."""
    fake = tmp_path / "gws"
    fake.write_text("x")
    with patch.object(_gws._binary, "resolve", return_value=str(fake)):
        yield


def _run(returncode=0, stdout="{}", stderr=""):
    proc = MagicMock(returncode=returncode, stdout=stdout, stderr=stderr)
    with patch.object(_gws.subprocess, "run", return_value=proc) as run:
        result = _gws.run(
            "drive",
            ["files"],
            "list",
            params={"pageSize": 5},
            opts={},
            pillar={},
        )
    return result, run.call_args


def test_argv_construction():
    _, call_args = _run(stdout='{"files": []}')
    argv = call_args.args[0]
    assert argv[1:] == [
        "drive",
        "files",
        "list",
        "--format",
        "json",
        "--params",
        '{"pageSize": 5}',
    ]


def test_body_and_test_flag():
    proc = MagicMock(returncode=0, stdout="{}", stderr="")
    with patch.object(_gws.subprocess, "run", return_value=proc) as run:
        _gws.run(
            "drive",
            ["files"],
            "create",
            body={"name": "f"},
            test=True,
            opts={},
            pillar={},
        )
    argv = run.call_args.args[0]
    assert "--json" in argv
    assert argv[argv.index("--json") + 1] == '{"name": "f"}'
    assert "--dry-run" in argv


def test_page_all_ndjson_returns_list():
    proc = MagicMock(returncode=0, stdout='{"a": 1}\n{"a": 2}\n', stderr="")
    with patch.object(_gws.subprocess, "run", return_value=proc):
        pages = _gws.run("drive", ["files"], "list", page_all=True, opts={}, pillar={})
    assert pages == [{"a": 1}, {"a": 2}]


def test_success_returns_parsed_dict():
    result, _ = _run(stdout='{"id": "abc"}')
    assert result == {"id": "abc"}


@pytest.mark.parametrize(
    "code,reason,fragment",
    [
        (1, "rateLimitExceeded", "API error"),
        (2, "authError", "authentication error"),
        (3, "validationError", "validation error"),
        (4, "notFound", "discovery error"),
        (5, "internal", "internal gws error"),
    ],
)
def test_exit_codes_map_to_exceptions(code, reason, fragment):
    payload = '{"error": {"code": 400, "message": "boom", "reason": "%s"}}' % reason
    with pytest.raises(_gws.CommandExecutionError) as exc:
        _run(returncode=code, stdout=payload)
    assert fragment in str(exc.value)
    assert "boom" in str(exc.value)


def test_error_without_json_body():
    with pytest.raises(_gws.CommandExecutionError, match="exited with code 5"):
        _run(returncode=5, stdout="", stderr="segfault")


def test_zero_exit_with_embedded_error():
    payload = '{"error": {"code": 403, "message": "denied", "reason": "forbidden"}}'
    with pytest.raises(_gws.CommandExecutionError, match="denied"):
        _run(returncode=0, stdout=payload)


def test_reserved_kwargs_split_from_params():
    proc = MagicMock(returncode=0, stdout="{}", stderr="")
    with patch.object(_gws.subprocess, "run", return_value=proc) as run:
        _gws.call(
            {"test": False},
            {},
            "drive",
            ["files"],
            "list",
            params={"pageSize": 5, "test": True, "page_all": True},
        )
    argv = run.call_args.args[0]
    assert "--dry-run" in argv  # test=True from params
    assert "--page-all" in argv
    # reserved keys must not leak into --params
    params_json = argv[argv.index("--params") + 1]
    assert "test" not in params_json
    assert "page_all" not in params_json


def test_test_flag_from_opts():
    proc = MagicMock(returncode=0, stdout="{}", stderr="")
    with patch.object(_gws.subprocess, "run", return_value=proc) as run:
        _gws.call({"test": True}, {}, "drive", ["files"], "list", params={"pageSize": 1})
    assert "--dry-run" in run.call_args.args[0]


def test_secret_never_on_argv():
    """Credentials go through env only, never argv."""
    proc = MagicMock(returncode=0, stdout="{}", stderr="")
    pillar = {"gsuite": {"auth": {"method": "token", "token": "ya29.SECRET"}}}
    with patch.object(_gws.subprocess, "run", return_value=proc) as run:
        _gws.run("drive", ["files"], "list", opts={}, pillar=pillar)
    argv = run.call_args.args[0]
    assert not any("ya29.SECRET" in str(a) for a in argv)
    env = run.call_args.kwargs["env"]
    assert env["GOOGLE_WORKSPACE_CLI_TOKEN"] == "ya29.SECRET"


def test_timeout_maps_to_error():
    with patch.object(
        _gws.subprocess, "run", side_effect=_gws.subprocess.TimeoutExpired("gws", 120)
    ):
        with pytest.raises(_gws.CommandExecutionError, match="timed out"):
            _gws.run("drive", ["files"], "list", opts={}, pillar={})
