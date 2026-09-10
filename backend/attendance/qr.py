"""Rotating tokens for the front-desk QR code.

Nothing is stored. The token is an HMAC over the current time window and the
project's secret key -- the same shape as a TOTP code -- so there is no table
to clean up and no row that can go stale. The clock is the state, which is the
same "derive it, don't store it" reasoning that keeps membership status out of
the database.

Why a rotating code at all: a static QR taped to the wall can be photographed
once and used from the car park forever. A code that changes every minute means
a member has to be standing in front of the screen to check in.
"""

from datetime import datetime

from django.conf import settings
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

# How long one code lives on screen.
WINDOW_SECONDS = 60
# Windows accepted besides the current one. A member scanning at :59 posts at
# :01, by which time the screen has already rotated -- without this they would
# get a spurious "expired" and try again.
GRACE_WINDOWS = 1

KEY_SALT = "attendance.qr.check-in"


def _window_at(moment):
    return int(moment.timestamp()) // WINDOW_SECONDS


def _sign(window):
    return salted_hmac(KEY_SALT, str(window), secret=settings.SECRET_KEY).hexdigest()[:32]


def current_token(now=None):
    """The code the kiosk should be showing, and the moment it stops being the
    current one. The kiosk refreshes on `expires_at`; the grace window covers
    the seconds either side of that."""
    now = now or timezone.now()
    window = _window_at(now)
    expires_at = datetime.fromtimestamp(
        (window + 1) * WINDOW_SECONDS, tz=timezone.get_current_timezone()
    )
    return _sign(window), expires_at


def is_valid(token, now=None):
    """True when `token` is the code from the current window or one of the
    grace windows just before it."""
    if not token:
        return False
    now = now or timezone.now()
    window = _window_at(now)
    # Every candidate is compared -- the list comprehension is deliberate,
    # since a short-circuiting `any(... for ...)` would leak through timing
    # which window a guess landed in.
    matches = [
        constant_time_compare(token, _sign(window - offset))
        for offset in range(GRACE_WINDOWS + 1)
    ]
    return any(matches)
