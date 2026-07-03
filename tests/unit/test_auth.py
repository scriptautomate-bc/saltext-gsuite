import json
import os
import stat

import pytest

from saltext.gsuite import _auth


@pytest.fixture
def opts(tmp_path):
    return {"cachedir": str(tmp_path / "cache")}


def test_token_method(opts):
    pillar = {"gsuite": {"auth": {"method": "token", "token": "ya29.abc"}}}
    with _auth.environment(pillar=pillar, opts=opts) as env:
        assert env[_auth.ENV_TOKEN] == "ya29.abc"
        assert _auth.ENV_CREDENTIALS_FILE not in env
        assert env[_auth.ENV_KEYRING_BACKEND] == "file"
        assert env[_auth.ENV_CONFIG_DIR]


def test_token_method_missing_token(opts):
    pillar = {"gsuite": {"auth": {"method": "token"}}}
    with pytest.raises(_auth.AuthError, match="no 'token'"):
        with _auth.environment(pillar=pillar, opts=opts):
            pass


def test_credentials_file(opts, tmp_path):
    creds = tmp_path / "creds.json"
    creds.write_text("{}")
    pillar = {"gsuite": {"auth": {"method": "credentials_file", "credentials_file": str(creds)}}}
    with _auth.environment(pillar=pillar, opts=opts) as env:
        assert env[_auth.ENV_CREDENTIALS_FILE] == str(creds)


def test_credentials_file_missing(opts, tmp_path):
    pillar = {
        "gsuite": {"auth": {"method": "credentials_file", "credentials_file": str(tmp_path / "x")}}
    }
    with pytest.raises(_auth.AuthError, match="does not exist"):
        with _auth.environment(pillar=pillar, opts=opts):
            pass


def test_service_account_inline_staged_and_cleaned(opts):
    sa = {"type": "service_account", "private_key": "SECRET", "client_email": "a@b.iam"}
    pillar = {"gsuite": {"auth": {"method": "service_account", "service_account": sa}}}
    staged = {}
    with _auth.environment(pillar=pillar, opts=opts) as env:
        path = env[_auth.ENV_CREDENTIALS_FILE]
        staged["path"] = path
        assert os.path.isfile(path)
        # 0600 permissions
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
        with open(path, encoding="utf-8") as handle:
            assert json.load(handle)["private_key"] == "SECRET"
    # cleaned up after the context exits
    assert not os.path.exists(staged["path"])


def test_service_account_inference_without_method(opts):
    sa = {"type": "service_account", "client_email": "a@b.iam"}
    pillar = {"gsuite": {"auth": {"service_account": sa}}}
    with _auth.environment(pillar=pillar, opts=opts) as env:
        assert os.path.isfile(env[_auth.ENV_CREDENTIALS_FILE])


def test_project_id_and_subject_warns(opts, caplog):
    pillar = {
        "gsuite": {
            "auth": {
                "method": "token",
                "token": "t",
                "project_id": "my-proj",
                "subject": "user@domain.com",
            }
        }
    }
    with _auth.environment(pillar=pillar, opts=opts) as env:
        assert env[_auth.ENV_PROJECT_ID] == "my-proj"
    assert any("delegation" in r.message for r in caplog.records)


def test_ambient_secrets_are_cleared(opts):
    base = {_auth.ENV_TOKEN: "leaked", _auth.ENV_ADC: "/leaked.json"}
    pillar = {"gsuite": {"auth": {"method": "adc"}}}
    with _auth.environment(pillar=pillar, opts=opts, base_env=base) as env:
        assert env.get(_auth.ENV_TOKEN) is None
        assert env.get(_auth.ENV_ADC) is None


def test_adc_explicit_path(opts):
    pillar = {"gsuite": {"auth": {"method": "adc", "application_credentials": "/etc/adc.json"}}}
    with _auth.environment(pillar=pillar, opts=opts) as env:
        assert env[_auth.ENV_ADC] == "/etc/adc.json"


def test_config_dir_from_pillar(tmp_path):
    cfg = tmp_path / "gwshome"
    pillar = {"gsuite": {"config_dir": str(cfg), "auth": {"method": "adc"}}}
    with _auth.environment(pillar=pillar, opts={}) as env:
        assert env[_auth.ENV_CONFIG_DIR] == str(cfg)
        assert os.path.isdir(str(cfg))
