"""
Post messages to a Google Chat space through an incoming webhook.

This module is hand written (everything else under ``modules/`` except
``gsuite_util`` is generated). Unlike the generated ``gsuite_chat`` module - which
drives the authenticated ``gws`` CLI - posting through an incoming webhook needs
**no** Google Workspace auth: the webhook URL itself is the credential (it embeds
the ``key`` and ``token`` query parameters that authorize the post). It is treated
like a secret and is never written to the logs (only the host and space id are
logged).

The HTTP request is made with ``requests``, which ships with every Salt install,
so no extra dependency is required. Two message shapes are supported:

* ``gsuite_chat_webhook.spaces_messages_send_simple`` - a plain/markdown ``text`` message,
* ``gsuite_chat_webhook.spaces_messages_send_rich`` - a rich ``cardsV2`` card, supplied as
  raw JSON (string or file) or assembled from convenience fields.

The webhook URL may be passed directly via ``webhook_url`` or looked up from pillar
by ``name`` at ``gsuite:chat:webhooks:<name>``.

CLI Examples:

.. code-block:: bash

    salt '*' gsuite_chat_webhook.spaces_messages_send_simple text='Deploy *finished*' webhook_url='https://chat.googleapis.com/v1/spaces/AAAA/messages?key=...&token=...'
    salt '*' gsuite_chat_webhook.spaces_messages_send_simple text='Deploy finished' name=alerts
    salt '*' gsuite_chat_webhook.spaces_messages_send_rich name=alerts title='Build 123' text='SUCCESS' button_text='Logs' button_url='https://ci.example.com/123'
"""

import json
import logging
from pathlib import Path
from urllib.parse import parse_qsl
from urllib.parse import urlencode
from urllib.parse import urlparse
from urllib.parse import urlunparse

try:
    import requests

    HAS_REQUESTS = True
except ImportError:  # pragma: no cover - requests ships with Salt
    HAS_REQUESTS = False

try:
    from salt.exceptions import CommandExecutionError
    from salt.exceptions import SaltInvocationError
except ImportError:  # pragma: no cover - allows importing outside a salt runtime

    class CommandExecutionError(Exception):
        """Fallback used when Salt is not importable."""

    class SaltInvocationError(Exception):
        """Fallback used when Salt is not importable."""


log = logging.getLogger(__name__)

__virtualname__ = "gsuite_chat_webhook"

# Host every legitimate Google Chat incoming webhook lives on.
WEBHOOK_HOST = "chat.googleapis.com"

# URL query param that lets a webhook message reply to (or start) a thread.
_REPLY_OPTION = "REPLY_MESSAGE_FALLBACK_TO_NEW_THREAD"

# Standard header for the Chat REST API.
_HEADERS = {"Content-Type": "application/json; charset=UTF-8"}


def __virtual__():
    if not HAS_REQUESTS:
        return (False, "The 'requests' library is required for gsuite_chat_webhook.")
    return __virtualname__


def _validate_webhook_url(webhook_url):
    """
    Return an error string if ``webhook_url`` is not a Google Chat webhook.

    Checks the URL is a non-empty ``https`` URL pointing at ``chat.googleapis.com``
    with a ``/v1/spaces/.../messages`` path. Returns ``None`` when the URL looks valid.
    """
    if not webhook_url or not webhook_url.strip():
        return "A webhook URL is required (pass webhook_url or name for a pillar lookup)."
    parsed = urlparse(webhook_url)
    if parsed.scheme != "https":
        return "Webhook URL must use https."
    if parsed.netloc != WEBHOOK_HOST:
        return f"Webhook URL host must be {WEBHOOK_HOST}, got '{parsed.netloc}'."
    if "/spaces/" not in parsed.path or not parsed.path.endswith("/messages"):
        return "Webhook URL path must look like /v1/spaces/<SPACE_ID>/messages."
    return None


def _resolve_webhook_url(webhook_url, name):
    """
    Return a validated webhook URL from ``webhook_url`` or a pillar ``name`` lookup.

    ``webhook_url`` takes precedence. When only ``name`` is given, the URL is read from
    pillar at ``gsuite:chat:webhooks:<name>``. Raises :class:`SaltInvocationError` if
    neither yields a valid Google Chat webhook URL.
    """
    if not webhook_url and name:
        webhook_url = __salt__["pillar.get"](f"gsuite:chat:webhooks:{name}")
        if not webhook_url:
            raise SaltInvocationError(
                f"No webhook URL found in pillar at gsuite:chat:webhooks:{name}."
            )
    error = _validate_webhook_url(webhook_url)
    if error:
        raise SaltInvocationError(error)
    return webhook_url


def _space_id_from_url(webhook_url):
    """Best-effort extraction of the space id from a webhook URL, for logging."""
    parts = urlparse(webhook_url).path.strip("/").split("/")
    if "spaces" in parts:
        idx = parts.index("spaces")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return "unknown"


def _with_reply_option(webhook_url):
    """Append ``messageReplyOption`` to the URL query, preserving key/token."""
    parsed = urlparse(webhook_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["messageReplyOption"] = _REPLY_OPTION
    return urlunparse(parsed._replace(query=urlencode(query)))


def _raise_http_error(exc):
    """Raise a :class:`CommandExecutionError`, parsing a ``google.rpc.Status`` body."""
    resp = exc.response
    status = resp.status_code if resp is not None else None
    message = ""
    if resp is not None:
        try:
            parsed = resp.json()
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            details = parsed.get("error", parsed)
            if isinstance(details, dict):
                message = str(details.get("message", ""))
    prefix = f"HTTP {status}" if status is not None else "HTTP error"
    if not message:
        message = str(exc)
    raise CommandExecutionError(f"Google Chat webhook post failed: {prefix}: {message}")


def _post(webhook_url, payload, thread_key=None):
    """
    POST ``payload`` to the Chat webhook and return the parsed response. HTTP chokepoint.

    When ``thread_key`` is set, adds ``thread.threadKey`` to the body and the
    ``messageReplyOption`` query param so the message groups into (or starts) a thread.
    Raises :class:`CommandExecutionError` on any HTTP or network failure. Never logs the
    credential-bearing URL.
    """
    url = webhook_url
    if thread_key:
        payload = {**payload, "thread": {"threadKey": thread_key}}
        url = _with_reply_option(webhook_url)

    space_id = _space_id_from_url(webhook_url)
    try:
        log.debug("gsuite_chat_webhook: POST to %s space=%s", WEBHOOK_HOST, space_id)
        resp = requests.post(url, json=payload, headers=_HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.exceptions.HTTPError as exc:
        _raise_http_error(exc)
    except requests.exceptions.RequestException as exc:
        raise CommandExecutionError(f"Google Chat webhook request failed: {exc}") from exc

    log.info("gsuite_chat_webhook: message posted to space=%s", space_id)
    try:
        body = resp.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _build_card(
    card_id="salt-card",
    title=None,
    subtitle=None,
    header_image_url=None,
    text=None,
    icon=None,
    button_text=None,
    button_url=None,
    image_url=None,
):
    """
    Assemble a minimal single-section ``cardsV2`` entry from convenience fields.

    Empty pieces are omitted. If ``icon`` is set, ``text`` is rendered as a
    ``decoratedText`` widget with a ``knownIcon`` start icon; otherwise as a
    ``textParagraph``. A button requires both ``button_text`` and ``button_url``.

    Returns a single card entry ``{"cardId": ..., "card": {...}}`` (not wrapped in
    ``cardsV2``); :func:`spaces_messages_send_rich` handles wrapping.
    """
    header = {}
    if title:
        header["title"] = title
    if subtitle:
        header["subtitle"] = subtitle
    if header_image_url:
        header["imageUrl"] = header_image_url

    widgets = []
    if text:
        if icon:
            widgets.append({"decoratedText": {"startIcon": {"knownIcon": icon}, "text": text}})
        else:
            widgets.append({"textParagraph": {"text": text}})
    if image_url:
        widgets.append({"image": {"imageUrl": image_url}})
    if button_text and button_url:
        widgets.append(
            {
                "buttonList": {
                    "buttons": [
                        {
                            "text": button_text,
                            "onClick": {"openLink": {"url": button_url}},
                        }
                    ]
                }
            }
        )

    card = {}
    if header:
        card["header"] = header
    if widgets:
        card["sections"] = [{"widgets": widgets}]
    return {"cardId": card_id, "card": card}


def _normalize_cards_payload(obj, default_card_id):
    """
    Coerce a user-supplied card object into a ``{"cardsV2": [...]}`` body.

    Accepts a full ``{"cardsV2": [...]}`` payload, a single card entry
    (``{"cardId": ..., "card": {...}}``), or a bare card object (``{"header": ...,
    "sections": ...}``). Returns ``None`` if ``obj`` is not a usable shape.
    """
    if not isinstance(obj, dict):
        return None
    if "cardsV2" in obj:
        return obj
    if "card" in obj:
        return {"cardsV2": [obj]}
    if "header" in obj or "sections" in obj:
        return {"cardsV2": [{"cardId": default_card_id, "card": obj}]}
    return None


def spaces_messages_send_simple(text, webhook_url=None, name=None, thread_key=None):
    """
    Post a plain/markdown text message to a Google Chat space via an incoming webhook.

    text
        Message body. Supports Chat markdown (``*bold*``, ``_italic_``,
        ``<url|label>``, ``<users/all>``, etc.). Required.
    webhook_url
        The full Google Chat incoming webhook URL (the credential). Takes precedence
        over ``name``.
    name
        Name of a webhook configured in pillar at ``gsuite:chat:webhooks:<name>``. Used
        when ``webhook_url`` is not given.
    thread_key
        Optional arbitrary key; messages sharing a key group into (or start) a thread.

    Returns the created message resource returned by the Chat API. Raises
    ``SaltInvocationError`` for bad input and ``CommandExecutionError`` on HTTP/network
    failure.

    CLI Example:

    .. code-block:: bash

        salt '*' gsuite_chat_webhook.spaces_messages_send_simple text='Deploy finished' name=alerts
        salt '*' gsuite_chat_webhook.spaces_messages_send_simple text='In thread' name=alerts thread_key=deploy-42
    """
    resolved = _resolve_webhook_url(webhook_url, name)
    if not text or not str(text).strip():
        raise SaltInvocationError("A non-empty message text is required.")
    return _post(resolved, {"text": text}, thread_key=thread_key)


def spaces_messages_send_rich(
    webhook_url=None,
    name=None,
    card_json=None,
    card_file=None,
    thread_key=None,
    card_id="salt-card",
    title=None,
    subtitle=None,
    header_image_url=None,
    text=None,
    icon=None,
    button_text=None,
    button_url=None,
    image_url=None,
):
    """
    Post a rich ``cardsV2`` message to a Google Chat space via an incoming webhook.

    Card source precedence: ``card_json`` (raw JSON string) > ``card_file`` (path to a
    JSON file) > the builder fields (assembled from ``title``/``text``/etc.). The parsed
    object may be a full ``{"cardsV2": [...]}`` payload, a single card entry, or a bare
    card object.

    webhook_url
        The full Google Chat incoming webhook URL (the credential). Takes precedence
        over ``name``.
    name
        Name of a webhook configured in pillar at ``gsuite:chat:webhooks:<name>``.
    card_json
        Raw JSON string describing the card(s).
    card_file
        Path to a JSON file describing the card(s).
    thread_key
        Optional arbitrary key; messages sharing a key group into (or start) a thread.
    card_id
        ``cardId`` used when building from fields or wrapping a bare card. Defaults to
        ``salt-card``.
    title, subtitle, header_image_url
        Card header fields (builder).
    text, icon
        Body text; when ``icon`` (a ``knownIcon`` name) is set the text renders as a
        ``decoratedText`` widget, otherwise as a ``textParagraph`` (builder).
    button_text, button_url
        Add a button (both required together) (builder).
    image_url
        Add an image widget (builder).

    Returns the created message resource returned by the Chat API. Raises
    ``SaltInvocationError`` for bad input and ``CommandExecutionError`` on HTTP/network
    failure.

    CLI Example:

    .. code-block:: bash

        salt '*' gsuite_chat_webhook.spaces_messages_send_rich name=alerts title='Build 123' text='SUCCESS' button_text='Logs' button_url='https://ci.example.com/123'
        salt '*' gsuite_chat_webhook.spaces_messages_send_rich name=alerts card_file=/srv/salt/cards/build.json
    """
    resolved = _resolve_webhook_url(webhook_url, name)

    if card_json is not None:
        try:
            raw = json.loads(card_json)
        except ValueError as exc:
            raise SaltInvocationError(f"Invalid card_json: {exc}") from exc
    elif card_file is not None:
        path = Path(card_file)
        if not path.is_file():
            raise SaltInvocationError(f"Card file not found: {card_file}")
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise SaltInvocationError(f"Invalid JSON in {card_file}: {exc}") from exc
        except OSError as exc:
            raise CommandExecutionError(f"Could not read {card_file}: {exc}") from exc
    else:
        raw = _build_card(
            card_id=card_id,
            title=title,
            subtitle=subtitle,
            header_image_url=header_image_url,
            text=text,
            icon=icon,
            button_text=button_text,
            button_url=button_url,
            image_url=image_url,
        )
        if not raw.get("card"):
            raise SaltInvocationError(
                "No card content provided. Pass card_json/card_file, or at least one of "
                "title/text/button_text+button_url/image_url."
            )

    payload = _normalize_cards_payload(raw, default_card_id=card_id)
    if payload is None:
        raise SaltInvocationError(
            "Unrecognized card structure. Expected a cardsV2 payload, a single "
            "{cardId, card} entry, or a bare card object with header/sections."
        )
    return _post(resolved, payload, thread_key=thread_key)
