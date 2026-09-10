"""Letting verified gym domains through Django's host and CORS checks.

Both lists were static env vars, which is fine for one deployment and wrong for
a platform: every gym that adds a domain would need a redeploy before their own
address worked, and an owner who has just completed DNS verification would
watch it 400.

So both become dynamic, and both draw from the same source -- a domain that has
proved ownership. Neither will admit an unverified one, which keeps the
verification step meaningful in a second place rather than only at the router.

Cached for a minute. A request cannot afford a database round trip just to
decide whether it is allowed to exist, and a domain going live a minute after
verification is not a problem anybody notices. The cache is cleared explicitly
when a domain is verified, so the common case is instant anyway.
"""

import logging

from django.core.cache import cache

logger = logging.getLogger(__name__)

CACHE_KEY = "tenancy:verified-hostnames"
CACHE_SECONDS = 60


def verified_hostnames():
    """Every hostname currently allowed to serve a gym."""
    cached = cache.get(CACHE_KEY)
    if cached is not None:
        return cached

    try:
        from .models import Domain

        names = list(
            Domain.unscoped.filter(verified_at__isnull=False)
            .values_list("hostname", flat=True)
        )
    except Exception:  # noqa: BLE001
        # Runs during `migrate` on an empty database and in any window where
        # the table does not exist yet. Returning nothing means the static
        # env hosts still work; raising here would take the site down.
        logger.debug("verified hostnames unavailable", exc_info=True)
        return []

    cache.set(CACHE_KEY, names, CACHE_SECONDS)
    return names


def forget_hostnames():
    """Drop the cache -- called when a domain is verified or removed."""
    cache.delete(CACHE_KEY)


class DynamicAllowedHosts(list):
    """`ALLOWED_HOSTS` that also admits verified gym domains.

    Django validates with `any(... for pattern in allowed_hosts)`, so iterating
    is the whole contract. Subclassing `list` keeps the configured static hosts
    working exactly as before -- the platform's own domain, localhost, the
    health check -- and appends the tenant ones.
    """

    def __iter__(self):
        yield from list.__iter__(self)
        yield from verified_hostnames()

    def __contains__(self, value):
        return list.__contains__(self, value) or value in verified_hostnames()


#: The one path that answers *any* origin.
#:
#: A gym's contact form lives on their marketing site -- `www.yourgym.com` --
#: which is a different host from the `app.yourgym.com` they verified for the
#: portal, and often not on this platform at all. Judging it by the verified
#: list would mean the form we hand them fails in every browser with a CORS
#: error, which is a hard thing for a gym owner to diagnose from a blank page.
#:
#: Opening it costs nothing, because the browser was never the thing keeping
#: anyone out: the key sits in public JavaScript, and anyone who wants to post
#: without a browser just uses curl, which CORS does not touch. What holds is
#: the endpoint's reach -- create one enquiry, read nothing -- plus the rate
#: limit. The reply is `{"received": true}` either way, so a page that is
#: allowed to read it learns nothing, and the endpoint authenticates on a
#: header alone, so a cookie sent alongside is ignored rather than trusted.
PUBLIC_LEAD_PATH = "/tenancy/leads/"


def cors_allow_verified_domain(sender, request, **kwargs):
    """`corsheaders` signal: approve a gym's own verified origin.

    The frontend is served from the gym's domain and calls the API on the
    platform's, so every custom domain is a cross-origin caller. Matching on
    the Origin header's hostname rather than the request's own host, because on
    a cross-origin call those are different -- and it is the *caller* being
    judged.
    """
    # Suffix, not equality: the tenant prefix is still on the path here, since
    # CorsMiddleware runs before the one that strips it.
    if request.path.endswith(PUBLIC_LEAD_PATH):
        return True

    origin = request.META.get("HTTP_ORIGIN")
    if not origin:
        return False
    from urllib.parse import urlparse

    hostname = (urlparse(origin).hostname or "").lower()
    return bool(hostname) and hostname in verified_hostnames()
