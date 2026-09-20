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

from .mfa import pending_user_id


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


class MfaAttemptThrottle(SimpleRateThrottle):
    """Guesses at a sign-in code, limited by the account they are aimed at.

    A six-digit code, with one step either side accepted for clock drift, is
    three chances in a million per guess. That is only small while guesses are
    few, so they are counted per account -- before a session exists, the
    pending token names it -- and in two windows: a burst limit here, and an
    hourly one below that caps what a patient attacker gets through in a day.
    Both come after the password, so this is the second wall, not the only one.

    The caveat in the module docstring applies: without a shared cache these
    counts are per process and reset on restart.
    """

    scope = "mfa_attempt"

    def get_cache_key(self, request, view):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            ident = user.pk
        else:
            data = getattr(request, "data", None)
            ident = pending_user_id(data.get("mfa_token")) if hasattr(data, "get") else None
        if ident is None:
            # No account to key on. The per-IP scope still applies, and the view
            # refuses a request without a valid pending token anyway.
            return None
        return self.cache_format % {"scope": self.scope, "ident": ident}


class MfaAttemptHourlyThrottle(MfaAttemptThrottle):
    scope = "mfa_attempt_hourly"


def _session_user_id(request):
    """The account behind the refresh cookie, if it is a genuine, unexpired
    refresh token; None otherwise.

    Signature and expiry only, with no blacklist lookup: this decides which
    bucket a request is counted in, not whether it is honoured -- the view still
    does the full check. Remembered on the request, since both refresh
    throttles ask.
    """
    if not hasattr(request, "_refresh_session_user_id"):
        from django.conf import settings
        from rest_framework_simplejwt.exceptions import TokenBackendError
        from rest_framework_simplejwt.settings import api_settings as jwt_settings
        from rest_framework_simplejwt.state import token_backend

        user_id = None
        raw = request.COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME)
        if raw:
            try:
                payload = token_backend.decode(raw, verify=True)
            except TokenBackendError:
                payload = {}
            if payload.get(jwt_settings.TOKEN_TYPE_CLAIM) == "refresh":
                user_id = payload.get(jwt_settings.USER_ID_CLAIM)
        request._refresh_session_user_id = user_id
    return request._refresh_session_user_id


class RefreshSessionThrottle(SimpleRateThrottle):
    """Refreshes of one genuine session, counted per account.

    Per account rather than per address because a gym's members share one
    internet connection. Counted per IP -- as they were, on the shared anonymous
    bucket -- a busy hour of the public website spent everybody's allowance, and
    members were signed out on their next reload.
    """

    scope = "refresh"

    def get_cache_key(self, request, view):
        user_id = _session_user_id(request)
        if user_id is None:
            return None
        return self.cache_format % {"scope": self.scope, "ident": user_id}


class RefreshAnonymousThrottle(SimpleRateThrottle):
    """Refresh attempts carrying no genuine session, counted per address.

    A signed-out visitor sends one of these per page load and is signed out
    whatever the answer, so this can be tight without costing anyone anything.
    """

    scope = "refresh_anonymous"

    def get_cache_key(self, request, view):
        if _session_user_id(request) is not None:
            return None
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}
