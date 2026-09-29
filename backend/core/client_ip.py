"""Which address a request came from, decided one way for the whole app.

Behind a reverse proxy the socket address belongs to the proxy, and the caller's
own address is one of the entries in `X-Forwarded-For` -- a header anybody can
put anything in. `NUM_PROXIES` says how many hops in front of this app append to
it, which is what makes one of those entries trustworthy: DRF counts that many
from the right and takes the address the nearest trusted proxy wrote.

The rate limiter already worked that out for itself. The security log did not --
it read `REMOTE_ADDR` directly, so with a proxy in front every audit line
recorded the proxy and the log disagreed with the limiter about who had done
something. This borrows the limiter's own implementation rather than repeating
it, so the two cannot drift apart.

`NUM_PROXIES` has no correct default: it depends on the deployment. It is 0 here
(trust only the socket address), which is right locally and deliberately
conservative in production -- with 0, a forged header changes nothing. The
production value has to be measured from the deployed request chain; see
"Confirming NUM_PROXIES" in the README.
"""

from rest_framework.throttling import BaseThrottle


def client_ip(request):
    """The caller's address, as the rate limiter counts it. "" when unknown."""
    if request is None:
        return ""
    return BaseThrottle().get_ident(request) or ""
