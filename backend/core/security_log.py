"""Security events: what happened, to whom and from where -- never the secret.

One call shape for every event, so they read alike in the log and can be
searched for by name (`security_event=login_failed`).

What may be written is an **allowlist**, not a denylist. A password, a code, a
token or a signature handed to `security_event` by mistake is dropped rather
than logged -- a denylist would have to anticipate every name a secret might be
passed under, and the one it missed would end up in the log. Values are
flattened to a single printable token, so a username with a newline in it
cannot forge a second, official-looking line.
"""

import logging

logger = logging.getLogger("security")

#: The only fields an event may carry.
FIELDS = ("user", "username", "target", "tenant", "ip", "reason", "count")

MAX_VALUE_LENGTH = 120


def _flatten(value):
    text = str(value)
    return "".join(ch if ch.isprintable() and not ch.isspace() else "_" for ch in text)[:MAX_VALUE_LENGTH]


def security_event(event, request=None, *, warning=False, **fields):
    """Record one security event. `warning` for things worth an alert."""
    data = {key: fields[key] for key in FIELDS if fields.get(key) not in (None, "")}
    if request is not None:
        data.setdefault("ip", request.META.get("REMOTE_ADDR", ""))
        from tenancy import context

        tenant = context.get()
        if tenant is not None:
            data.setdefault("tenant", tenant.slug)
    detail = " ".join(f"{key}={_flatten(value)}" for key, value in data.items() if value not in (None, ""))
    logger.log(
        logging.WARNING if warning else logging.INFO,
        "security_event=%s %s",
        _flatten(event),
        detail,
    )
