"""Revoking a user's outstanding refresh tokens.

Access tokens are stateless and short-lived (15 minutes); refresh tokens are
not, and they live for a week. That difference is the whole reason this module
exists: changing a password rewrites the hash, but it does nothing to a refresh
token already in somebody's hands. Without this, resetting the password of an
account you believe is compromised leaves whoever took it logged in for up to
seven more days -- which is precisely the moment the reset was meant to stop.

Blacklisting is best-effort by design. It runs off `token_blacklist`'s own
tables, and a failure to revoke must never be the reason a password change is
refused: a changed password with stale sessions is strictly better than an
unchanged one.
"""

import logging

from core.security_log import security_event

logger = logging.getLogger(__name__)


def revoke_refresh_tokens(user):
    """Blacklist every outstanding refresh token belonging to `user`.

    Returns the number blacklisted. Tokens already blacklisted are counted
    once, not twice -- `get_or_create` keeps a repeated call idempotent, which
    matters because an admin correcting a typo may save the same form twice.
    """
    try:
        from rest_framework_simplejwt.token_blacklist.models import (
            BlacklistedToken,
            OutstandingToken,
        )
    except ImportError:  # pragma: no cover -- blacklist app not installed
        logger.warning("token_blacklist is not installed; cannot revoke tokens")
        return 0

    # The database first, and this ordering is the point.
    #
    # Two things end a session, and they are not equally durable: blacklisting
    # the refresh tokens is a row in a table that survives anything, while
    # ending the access tokens is a note in a cache that may be unreachable.
    # Ending the access tokens first meant that when the cache was down its
    # exception left this function before a single refresh token had been
    # blacklisted -- so a password reset meant to lock an intruder out changed
    # the password and left them a refresh token good for another week. The
    # durable half now happens first and cannot be skipped by a cache outage.
    revoked = 0
    for token in OutstandingToken.objects.filter(user=user):
        try:
            _, created = BlacklistedToken.objects.get_or_create(token=token)
        except Exception:  # noqa: BLE001 -- see the module docstring
            logger.exception("could not blacklist token %s for user %s", token.pk, user.pk)
            continue
        revoked += int(created)

    # Then the short-lived half. Access tokens already handed out would
    # otherwise keep working for up to fifteen minutes after the reset that was
    # meant to lock someone out. See accounts.revocation.
    #
    # A failure here is reported rather than swallowed -- the caller is told
    # that half the job is undone -- but it is recorded first, so the log says
    # plainly that the refresh tokens did go and the access tokens did not.
    from .revocation import RevocationUnavailable, end_access_tokens

    try:
        end_access_tokens(user)
    except RevocationUnavailable:
        security_event(
            "access_tokens_not_ended",
            warning=True,
            user=user.pk,
            count=revoked,
            reason="revocation_store_unavailable",
        )
        raise

    return revoked
