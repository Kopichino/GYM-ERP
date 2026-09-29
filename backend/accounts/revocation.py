"""Ending access tokens before they expire.

Access tokens are stateless, which is what makes them cheap -- and what means
that, on their own, nothing can stop one early. A token taken from a browser
keeps working for its full fifteen minutes after the owner logs out, changes
their password or has an admin reset their sign-in. These close that window.

Two records, both in the cache and both only kept for as long as an access
token could still be live, so neither needs a table or a clean-up job:

* **one token** -- logging out ends the token that logged out, and no other, so
  signing out of the phone leaves the laptop signed in;
* **every token issued before a moment** -- a password change or reset ends
  every session that was open when it happened. Compared to the second: a
  token minted in the same second as the cut-off is honoured, which is what
  lets the page that changed the password keep working.

With a per-process cache (LocMemCache) a revocation is only seen by the worker
that recorded it. Production has to run on a shared cache (REDIS_URL) for these
to hold across workers -- `core.checks` warns when it does not.

This reads and writes the `revocation` cache, which is deliberately **not** the
resilient one the throttles use. If it cannot be reached, the honest answer to
"has this session been ended?" is "I cannot tell", and the safe thing to do with
that answer is refuse: a `RevocationUnavailable` (503), never a quiet "no".
Otherwise the first thing a Redis outage would restore is every session somebody
had just logged out of. See core.cache.
"""

import time

from django.conf import settings
from django.core.cache import caches
from rest_framework.exceptions import APIException
from rest_framework_simplejwt.settings import api_settings as jwt_settings

from core.cache import redis_error_class


class RevocationUnavailable(APIException):
    """The revocation store is unreachable, so nothing may be taken on trust."""

    status_code = 503
    default_detail = "Sign-in state is temporarily unavailable. Please try again."
    default_code = "revocation_unavailable"


def _cache():
    return caches["revocation"]


def _access_lifetime():
    return int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds())


def _token_key(jti):
    return f"auth:revoked-access:{jti}"


def _cutoff_key(user_id):
    return f"auth:sessions-ended-at:{user_id}"


def revoke_access_token(token):
    """End this one access token now."""
    payload = getattr(token, "payload", None) or {}
    jti = payload.get(jwt_settings.JTI_CLAIM)
    if not jti:
        return
    remaining = int(payload.get("exp", 0) - time.time())
    try:
        _cache().set(_token_key(jti), 1, timeout=max(remaining, 1))
    except redis_error_class() as error:
        # Logging out has to fail loudly: reporting success while the record
        # never landed would leave the session alive and the member sure it was
        # not.
        raise RevocationUnavailable() from error


def end_access_tokens(user):
    """End every access token `user` was issued before this second."""
    try:
        _cache().set(
            _cutoff_key(user.pk), int(time.time()), timeout=_access_lifetime() + 60
        )
    except redis_error_class() as error:
        raise RevocationUnavailable() from error


def is_revoked(token):
    payload = getattr(token, "payload", None) or {}
    jti = payload.get(jwt_settings.JTI_CLAIM)
    try:
        if jti and _cache().get(_token_key(jti)):
            return True
        cutoff = _cache().get(_cutoff_key(payload.get(jwt_settings.USER_ID_CLAIM)))
    except redis_error_class() as error:
        # Fail closed. "I cannot reach the record" is not "there is no record".
        raise RevocationUnavailable() from error
    issued = payload.get("iat")
    return cutoff is not None and issued is not None and int(issued) < int(cutoff)
