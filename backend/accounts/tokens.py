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

    # Refresh tokens are the long-lived half; the access tokens already handed
    # out would otherwise keep working for up to fifteen minutes after the
    # reset that was meant to lock someone out. See accounts.revocation.
    from .revocation import end_access_tokens

    end_access_tokens(user)

    revoked = 0
    for token in OutstandingToken.objects.filter(user=user):
        try:
            _, created = BlacklistedToken.objects.get_or_create(token=token)
        except Exception:  # noqa: BLE001 -- see the module docstring
            logger.exception("could not blacklist token %s for user %s", token.pk, user.pk)
            continue
        revoked += int(created)
    return revoked
