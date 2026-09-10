"""Slowing down credential guessing.

The existing `login` scope throttles by client IP. That stops one machine
hammering the endpoint, and does nothing about the attack that actually
matters: a list of stolen passwords tried against one known account from a
different address each time. Every request looks like a first attempt.

So this throttles by the *username being attempted* as well. The two run
together -- an attacker is limited both by where they are coming from and by
whose account they are aiming at.

Deliberately a throttle and not a lockout. A hard lockout on repeated failures
hands anyone who knows a username a way to lock the owner out of their own gym,
which turns an availability problem into a support call. A short rolling window
costs an attacker almost everything and costs a member who fat-fingers their
password a minute.

One caveat, and it is a real one: throttle state lives in Django's cache, and
this project configures none -- so it is `LocMemCache`, which is per-process and
is wiped whenever the process restarts. On Render's free tier the service sleeps
after fifteen minutes idle, so in practice an attacker gets a fresh budget
after any quiet spell, and a second gunicorn worker would keep its own separate
count. Making this hold properly needs a shared cache (Redis); see the security
notes in the README.
"""

from rest_framework.throttling import SimpleRateThrottle


class LoginAttemptThrottle(SimpleRateThrottle):
    """Rate-limit by the username being attempted, whatever the source IP."""

    scope = "login_attempt"

    def get_cache_key(self, request, view):
        username = request.data.get("username") if hasattr(request, "data") else None
        if not isinstance(username, str):
            return None
        username = username.strip().lower()
        if not username:
            # Nothing to key on. The IP-based throttles still apply, so a
            # malformed flood is not unlimited.
            return None
        return self.cache_format % {"scope": self.scope, "ident": username}
