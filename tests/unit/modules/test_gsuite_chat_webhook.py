from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import requests

from saltext.gsuite.modules import gsuite_chat_webhook as mod

WEBHOOK = "https://chat.googleapis.com/v1/spaces/AAAA/messages?key=k&token=t"


@pytest.fixture
def pillar_get():
    """The mocked ``pillar.get`` injected into ``__salt__`` (asserted on directly)."""
    return MagicMock(return_value=WEBHOOK)


@pytest.fixture
def configure_loader_modules(pillar_get):
    return {
        mod: {
            "__opts__": {"test": False},
            "__pillar__": {},
            "__salt__": {"pillar.get": pillar_get},
        }
    }


def _fake_response(json_body=None, raise_exc=None):
    resp = MagicMock()
    resp.json.return_value = json_body if json_body is not None else {"name": "msg/1"}
    if raise_exc is not None:
        resp.raise_for_status.side_effect = raise_exc
    else:
        resp.raise_for_status.return_value = None
    return resp


def test_virtual_available():
    with patch.object(mod, "HAS_REQUESTS", True):
        assert mod.__virtual__() == "gsuite_chat_webhook"


def test_virtual_missing_requests():
    with patch.object(mod, "HAS_REQUESTS", False):
        result = mod.__virtual__()
    assert result[0] is False
    assert "requests" in result[1]


def test_send_simple_success():
    resp = _fake_response({"name": "spaces/AAAA/messages/1"})
    with patch.object(mod.requests, "post", return_value=resp) as post:
        ret = mod.spaces_messages_send_simple("hello", webhook_url=WEBHOOK)
    assert ret == {"name": "spaces/AAAA/messages/1"}
    args, kwargs = post.call_args
    assert args[0] == WEBHOOK
    assert kwargs["json"] == {"text": "hello"}
    assert kwargs["headers"] == mod._HEADERS


def test_send_simple_name_pillar_lookup(pillar_get):
    resp = _fake_response()
    with patch.object(mod.requests, "post", return_value=resp) as post:
        mod.spaces_messages_send_simple("hi", name="alerts")
    pillar_get.assert_called_once_with("gsuite:chat:webhooks:alerts")
    assert post.call_args.args[0] == WEBHOOK


def test_send_simple_name_not_in_pillar(pillar_get):
    pillar_get.return_value = None
    with pytest.raises(mod.SaltInvocationError):
        mod.spaces_messages_send_simple("hi", name="missing")


def test_send_simple_empty_text():
    with pytest.raises(mod.SaltInvocationError):
        mod.spaces_messages_send_simple("   ", webhook_url=WEBHOOK)


@pytest.mark.parametrize(
    "url",
    [
        "",
        "http://chat.googleapis.com/v1/spaces/A/messages",
        "https://evil.example.com/v1/spaces/A/messages",
        "https://chat.googleapis.com/v1/spaces/A/other",
    ],
)
def test_send_simple_invalid_url(url):
    with pytest.raises(mod.SaltInvocationError):
        mod.spaces_messages_send_simple("hi", webhook_url=url)


def test_send_simple_http_error():
    err_resp = MagicMock()
    err_resp.status_code = 400
    err_resp.json.return_value = {"error": {"message": "Invalid argument"}}
    http_err = requests.exceptions.HTTPError(response=err_resp)
    resp = _fake_response(raise_exc=http_err)
    resp.status_code = 400
    with patch.object(mod.requests, "post", return_value=resp):
        with pytest.raises(mod.CommandExecutionError) as exc:
            mod.spaces_messages_send_simple("hi", webhook_url=WEBHOOK)
    assert "400" in str(exc.value)
    assert "Invalid argument" in str(exc.value)


def test_send_simple_network_error():
    with patch.object(
        mod.requests,
        "post",
        side_effect=requests.exceptions.ConnectionError("boom"),
    ):
        with pytest.raises(mod.CommandExecutionError):
            mod.spaces_messages_send_simple("hi", webhook_url=WEBHOOK)


def test_thread_key_adds_thread_and_reply_option():
    resp = _fake_response()
    with patch.object(mod.requests, "post", return_value=resp) as post:
        mod.spaces_messages_send_simple("hi", webhook_url=WEBHOOK, thread_key="dep-42")
    args, kwargs = post.call_args
    assert kwargs["json"]["thread"] == {"threadKey": "dep-42"}
    assert "messageReplyOption=REPLY_MESSAGE_FALLBACK_TO_NEW_THREAD" in args[0]
    # key/token preserved
    assert "key=k" in args[0] and "token=t" in args[0]


def test_send_rich_builder_fields():
    resp = _fake_response()
    with patch.object(mod.requests, "post", return_value=resp) as post:
        mod.spaces_messages_send_rich(
            webhook_url=WEBHOOK,
            title="Build 123",
            text="SUCCESS",
            button_text="Logs",
            button_url="https://ci/123",
        )
    payload = post.call_args.kwargs["json"]
    card = payload["cardsV2"][0]["card"]
    assert card["header"]["title"] == "Build 123"
    widgets = card["sections"][0]["widgets"]
    assert {"textParagraph": {"text": "SUCCESS"}} in widgets
    assert any("buttonList" in w for w in widgets)


def test_send_rich_builder_icon_makes_decorated_text():
    resp = _fake_response()
    with patch.object(mod.requests, "post", return_value=resp) as post:
        mod.spaces_messages_send_rich(webhook_url=WEBHOOK, text="hi", icon="CLOCK")
    widgets = post.call_args.kwargs["json"]["cardsV2"][0]["card"]["sections"][0]["widgets"]
    assert widgets[0]["decoratedText"]["startIcon"]["knownIcon"] == "CLOCK"


def test_send_rich_card_json_full_payload():
    resp = _fake_response()
    full = '{"cardsV2": [{"cardId": "x", "card": {"header": {"title": "T"}}}]}'
    with patch.object(mod.requests, "post", return_value=resp) as post:
        mod.spaces_messages_send_rich(webhook_url=WEBHOOK, card_json=full)
    assert post.call_args.kwargs["json"]["cardsV2"][0]["cardId"] == "x"


def test_send_rich_card_json_bare_card_wrapped():
    resp = _fake_response()
    bare = '{"header": {"title": "T"}}'
    with patch.object(mod.requests, "post", return_value=resp) as post:
        mod.spaces_messages_send_rich(webhook_url=WEBHOOK, card_json=bare, card_id="cc")
    payload = post.call_args.kwargs["json"]
    assert payload["cardsV2"][0]["cardId"] == "cc"
    assert payload["cardsV2"][0]["card"] == {"header": {"title": "T"}}


def test_send_rich_card_file(tmp_path):
    resp = _fake_response()
    card = tmp_path / "card.json"
    card.write_text('{"cardId": "f", "card": {"sections": []}}', encoding="utf-8")
    with patch.object(mod.requests, "post", return_value=resp) as post:
        mod.spaces_messages_send_rich(webhook_url=WEBHOOK, card_file=str(card))
    assert post.call_args.kwargs["json"]["cardsV2"][0]["cardId"] == "f"


def test_send_rich_bad_card_json():
    with pytest.raises(mod.SaltInvocationError):
        mod.spaces_messages_send_rich(webhook_url=WEBHOOK, card_json="{not json")


def test_send_rich_missing_card_file():
    with pytest.raises(mod.SaltInvocationError):
        mod.spaces_messages_send_rich(webhook_url=WEBHOOK, card_file="/no/such/file.json")


def test_send_rich_no_content():
    with pytest.raises(mod.SaltInvocationError):
        mod.spaces_messages_send_rich(webhook_url=WEBHOOK)


def test_send_rich_unrecognized_structure():
    with pytest.raises(mod.SaltInvocationError):
        mod.spaces_messages_send_rich(webhook_url=WEBHOOK, card_json='{"foo": "bar"}')
