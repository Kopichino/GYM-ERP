"""WhatsApp Cloud API, spoken to over Meta's Graph endpoint.

Off unless credentials are configured, and honest about it: nothing here
pretends to send. A gym without a verified WhatsApp Business account gets email
reminders and no WhatsApp tab, rather than messages that silently vanish.

Two Meta-specific rules shape this module:

* Outside a 24-hour window from the member's last message, only pre-approved
  *template* messages may be sent. Free-form replies are for conversations the
  member started. `send_template` and `send_text` are separate for that reason,
  and the reminder sweep uses the template one.
* The webhook is verified twice -- a token handshake when Meta first subscribes,
  and an HMAC on every delivery.
"""

import hashlib
import hmac

import requests
from django.conf import settings
from django.utils.crypto import constant_time_compare

GRAPH_ROOT = "https://graph.facebook.com/v21.0"
TIMEOUT = 15


class WhatsAppError(Exception):
    """A send that failed, with something worth logging against the message."""


def _token():
    return getattr(settings, "WHATSAPP_TOKEN", "")


def _phone_number_id():
    return getattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "")


def is_configured():
    return bool(_token() and _phone_number_id())


def _post(payload):
    if not is_configured():
        raise WhatsAppError("WhatsApp isn't set up for this gym yet.")
    try:
        response = requests.post(
            f"{GRAPH_ROOT}/{_phone_number_id()}/messages",
            headers={"Authorization": f"Bearer {_token()}"},
            json=payload,
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        raise WhatsAppError("Could not reach WhatsApp.") from exc

    if response.status_code >= 400:
        detail = ""
        try:
            detail = response.json().get("error", {}).get("message", "")
        except ValueError:
            pass
        raise WhatsAppError(detail or "WhatsApp rejected that message.")

    body = response.json()
    messages = body.get("messages") or [{}]
    return messages[0].get("id", "")


def send_text(to_phone, body):
    """A free-form reply. Only valid inside the 24-hour service window, which
    is why this is used for replies and never for the reminder sweep."""
    return _post(
        {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "text",
            "text": {"body": body[:4096]},
        }
    )


def send_template(to_phone, template, language="en", parameters=None):
    """A pre-approved template, which is what may be sent unprompted."""
    components = []
    if parameters:
        components.append(
            {
                "type": "body",
                "parameters": [{"type": "text", "text": str(p)} for p in parameters],
            }
        )
    return _post(
        {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "template",
            "template": {
                "name": template,
                "language": {"code": language},
                **({"components": components} if components else {}),
            },
        }
    )


def verify_subscription(mode, token, challenge):
    """Meta's one-time handshake when the webhook is first subscribed.

    Returns the challenge to echo back, or None to refuse. Getting this wrong
    means Meta silently stops delivering, so it is refused loudly rather than
    defaulted to "allow".
    """
    expected = getattr(settings, "WHATSAPP_VERIFY_TOKEN", "")
    if mode == "subscribe" and expected and constant_time_compare(token or "", expected):
        return challenge
    return None


def verify_signature(raw_body, header):
    """Whether a webhook body really came from Meta.

    The header is "sha256=<hex>", signed with the app secret. Without an app
    secret configured this returns False: an unverifiable webhook is refused,
    never waved through.
    """
    secret = getattr(settings, "WHATSAPP_APP_SECRET", "")
    if not secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return constant_time_compare(header.split("=", 1)[1], expected)


def parse_incoming(payload):
    """Pulls (phone, text, message_id) out of Meta's nested webhook shape.

    Yields nothing for the delivery-receipt and status webhooks, which arrive on
    the same endpoint and are not messages.
    """
    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value", {}) or {}
            for message in value.get("messages", []) or []:
                if message.get("type") != "text":
                    # Images, audio and buttons land here too; the assistant
                    # only reads text, so the rest is acknowledged and skipped.
                    continue
                yield (
                    message.get("from", ""),
                    (message.get("text", {}) or {}).get("body", ""),
                    message.get("id", ""),
                )
