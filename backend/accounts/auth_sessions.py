"""Opening, recognising and ending sign-in sessions.

This sits *on* the refresh-token mechanism rather than beside it. Signing in
still produces one refresh token in one httpOnly cookie, rotated on every use,
blacklisted by SimpleJWT, ended early by the existing revocation paths. What is
added is a row (`AuthSession`) that the token points at through a random secret
claim, so that:

* the session has a **ceiling** that using it never moves;
* a session can be **listed and revoked on its own**, one device at a time;
* "remember me" and "trust this device" are real server-side facts, not a
  checkbox the browser remembers.

The secret is a long random string carried only inside the signed refresh token
(`sid`). The database holds its SHA-256 and nothing else, and it is stripped from
the access token, which JavaScript can read.
"""

import hashlib
import re
import secrets

from django.db import transaction
from django.utils import timezone
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.utils import datetime_from_epoch

from .models import AuthSession
from .session_policy import NORMAL, REMEMBER, TRUSTED, max_age_for

#: The claim in the refresh token that names its session. Never copied to the
#: access token.
SECRET_CLAIM = "sid"

_TRUE = {"1", "true", "yes", "on"}


# ---------------------------------------------------------------- the secret


def new_secret():
    """256 bits from the operating system's generator, URL-safe."""
    return secrets.token_urlsafe(32)


def hash_secret(secret):
    """Fast and unsalted is right: the secret is random, not chosen, so there is
    no dictionary to run against it. What the hash buys is that a copy of the
    database does not hand over anything a cookie could be built from."""
    return hashlib.sha256(str(secret).encode()).hexdigest()


# ---------------------------------------------------------------- choosing a kind


def flag(value):
    """A checkbox as the browser sends it. Strict: anything unrecognised is off."""
    if value is True:
        return True
    if isinstance(value, int) and not isinstance(value, bool):
        return value == 1
    return isinstance(value, str) and value.strip().lower() in _TRUE


def kind_for_login(remember, trust):
    """Trusting a device is the stronger choice, so ticking both gives that."""
    if flag(trust):
        return TRUSTED
    if flag(remember):
        return REMEMBER
    return NORMAL


# ---------------------------------------------------------------- labelling a device


_BROWSERS = (
    (r"Edg(e|A|iOS)?/", "Edge"),
    (r"OPR/|Opera", "Opera"),
    (r"Firefox/|FxiOS/", "Firefox"),
    (r"SamsungBrowser/", "Samsung Internet"),
    (r"Chrome/|CriOS/", "Chrome"),
    (r"Safari/", "Safari"),
)
_SYSTEMS = (
    (r"iPhone|iPad|iPod", "iOS"),
    (r"Android", "Android"),
    (r"Windows", "Windows"),
    (r"CrOS", "ChromeOS"),
    (r"Macintosh|Mac OS X", "macOS"),
    (r"Linux|X11", "Linux"),
)


def device_label(user_agent):
    """A name a person would recognise, like "Chrome on Windows".

    Deliberately all that is kept of the user agent: no version, no build, nothing
    that distinguishes one person's laptop from another's. It exists so a list of
    sessions can say which is which, not to fingerprint anybody.
    """
    agent = str(user_agent or "").strip()
    if not agent:
        return "Unknown device"
    browser = next((name for pattern, name in _BROWSERS if re.search(pattern, agent)), "Unknown browser")
    system = next((name for pattern, name in _SYSTEMS if re.search(pattern, agent)), "Unknown system")
    return f"{browser} on {system}"[:120]


# ---------------------------------------------------------------- opening a session


def start_session(user, kind, request=None):
    """Record a new session and return `(session, secret)`.

    The ceiling is worked out here from the settings as they stand now, and is the
    one place it is ever set.
    """
    secret = new_secret()
    agent = request.META.get("HTTP_USER_AGENT", "") if request is not None else ""
    session = AuthSession.objects.create(
        user=user,
        kind=kind,
        secret_hash=hash_secret(secret),
        label=device_label(agent),
        expires_at=timezone.now() + max_age_for(kind),
    )
    return session, secret


def ceiling(session):
    """The instant the session ends, as the epoch second a token's `exp` holds."""
    return int(session.expires_at.timestamp())


def seconds_left(session):
    """How long a cookie for this session should last. At least one second, so a
    session about to end still gets a cookie the browser will accept."""
    return max(int((session.expires_at - timezone.now()).total_seconds()), 1)


def mint_refresh(user, session, secret):
    """The refresh token for `session`: signed, naming the session, ending at its ceiling."""
    refresh = RefreshToken.for_user(user)
    refresh[SECRET_CLAIM] = secret
    refresh.payload["exp"] = ceiling(session)
    # `for_user` recorded the token as outstanding before it had the right expiry
    # or secret. Revoking an account's tokens finds them through that row, so it
    # has to describe the token that was actually handed out.
    OutstandingToken.objects.filter(jti=refresh[jwt_settings.JTI_CLAIM]).update(
        token=str(refresh), expires_at=datetime_from_epoch(refresh["exp"])
    )
    note_token(session, refresh)
    return refresh


def note_token(session, refresh):
    """Remember which refresh token is current, and that the session was just used."""
    now = timezone.now()
    jti = refresh[jwt_settings.JTI_CLAIM]
    AuthSession.objects.filter(pk=session.pk).update(current_jti=jti, last_seen_at=now)
    session.current_jti, session.last_seen_at = jti, now


def access_for(refresh):
    """The short-lived access token for `refresh`, without the session secret.

    SimpleJWT copies a refresh token's custom claims into the access token. This
    one is readable by any script on the page, so the secret is taken back out.
    """
    access = refresh.access_token
    access.payload.pop(SECRET_CLAIM, None)
    return access


def open_session(user, kind, request=None):
    """Start a session and mint its first refresh token, or neither."""
    with transaction.atomic():
        session, secret = start_session(user, kind, request)
        refresh = mint_refresh(user, session, secret)
    return session, refresh


# ---------------------------------------------------------------- finding one again


def find_session(secret, user):
    """The session a secret names, for this user, or None. Says nothing about
    whether it is still good: see `AuthSession.is_live`."""
    if not secret:
        return None
    return AuthSession.objects.filter(secret_hash=hash_secret(secret), user_id=user.pk).first()


def session_from_cookie(request):
    """The signed-in user's own session behind the refresh cookie, or None.

    Only the signature and expiry are checked, because all that is wanted is
    *which session this browser holds*: a token one rotation behind still names it.
    """
    from django.conf import settings
    from rest_framework_simplejwt.state import token_backend

    raw = request.COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME)
    user = getattr(request, "user", None)
    if not raw or user is None or not user.is_authenticated:
        return None
    try:
        secret = token_backend.decode(raw, verify=True).get(SECRET_CLAIM)
    except Exception:  # noqa: BLE001 -- an unreadable cookie names nothing
        return None
    return find_session(secret, user)


def kind_from_request(request):
    """The kind of session this browser is in, so a re-issued one can match it."""
    session = session_from_cookie(request)
    return session.kind if session is not None and session.is_live else NORMAL


# ---------------------------------------------------------------- ending sessions


def end_session(session):
    """Revoke one session. Idempotent; the first revocation's time is kept."""
    return AuthSession.objects.filter(pk=session.pk, revoked_at__isnull=True).update(
        revoked_at=timezone.now()
    )


def end_all_sessions(user):
    """Revoke every session of `user`. Returns how many were still live."""
    return AuthSession.objects.filter(user=user, revoked_at__isnull=True).update(
        revoked_at=timezone.now()
    )
