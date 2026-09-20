"""Two-step sign-in: authenticator-app codes and recovery codes.

TOTP is RFC 6238 on top of RFC 4226 HOTP, written here on the standard library
rather than pulled in as a dependency. It is a few dozen lines of precisely
specified arithmetic, checked in `tests_mfa.py` against the RFC's own test
vectors -- and no new package means nothing new to vet, pin or patch.

Two-step sign-in belongs to the *person*, not to a gym. Like the password it
covers every gym the account belongs to, so nothing here is tenant-scoped.
"""

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote, urlencode

from django.conf import settings
from django.core import signing

DIGITS = 6
PERIOD = 30

#: Codes from one step either side are accepted, for a phone whose clock is a
#: little out. A wider window buys tolerance a correctly synced phone never
#: needs, at the cost of more guesses landing.
DRIFT_STEPS = 1

RECOVERY_CODE_COUNT = 10
#: No 0/o or 1/l/i: a recovery code is read off paper, often long after it was
#: printed, by someone already locked out and in a hurry.
RECOVERY_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"

#: How long a correct password is good for while the second step is completed.
#: Long enough to find the authenticator app -- or to install one and set it up
#: for the first time -- and short enough that a pending token found later is
#: worthless.
PENDING_MAX_AGE = 10 * 60
PENDING_SALT = "accounts.mfa.pending-sign-in"


# ---------------------------------------------------------------- TOTP


def new_secret():
    """A fresh 160-bit key, base32 without padding, as authenticator apps expect."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _key(secret):
    cleaned = secret.replace(" ", "").upper()
    return base64.b32decode(cleaned + "=" * (-len(cleaned) % 8))


def hotp(secret, counter, digits=DIGITS):
    """RFC 4226: the code for one counter value."""
    mac = hmac.new(_key(secret), struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    value = struct.unpack(">I", mac[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % (10**digits)).zfill(digits)


def current_step(now=None):
    """RFC 6238: which 30-second window `now` falls in."""
    return int((time.time() if now is None else now) // PERIOD)


def matching_step(secret, code, *, after=None, now=None):
    """The time step `code` belongs to, or None if it matches nothing in the window.

    `after` is the last step this device already accepted a code for. A code
    for that step or earlier is refused even while still inside the window, so
    a code read over someone's shoulder cannot be replayed in the same
    half-minute.
    """
    digits = "".join(ch for ch in str(code or "") if ch.isdigit())
    if len(digits) != DIGITS or not secret:
        return None

    step = current_step(now)
    # The current step first, so a correct code never uses up a future step.
    candidates = [step]
    for drift in range(1, DRIFT_STEPS + 1):
        candidates += [step - drift, step + drift]

    for candidate in candidates:
        if after is not None and candidate <= after:
            continue
        if hmac.compare_digest(hotp(secret, candidate), digits):
            return candidate
    return None


def issuer():
    """The name the authenticator app files this account under."""
    return getattr(settings, "MFA_ISSUER", "") or "IRONCORE"


def provisioning_uri(secret, account_name):
    """The otpauth:// link an authenticator app reads from the setup QR code."""
    name = issuer()
    label = quote(f"{name}:{account_name}", safe="")
    query = urlencode(
        {"secret": secret, "issuer": name, "algorithm": "SHA1", "digits": DIGITS, "period": PERIOD}
    )
    return f"otpauth://totp/{label}?{query}"


# ---------------------------------------------------------------- recovery codes


def new_recovery_codes():
    """Ten codes of ten characters each (about 50 bits), shown as xxxxx-xxxxx."""

    def one():
        chars = "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(10))
        return f"{chars[:5]}-{chars[5:]}"

    # A set, so a (vanishingly unlikely) repeat cannot trip the unique index.
    codes = set()
    while len(codes) < RECOVERY_CODE_COUNT:
        codes.add(one())
    return sorted(codes)


def normalise_recovery_code(code):
    """Case, spaces and the dash do not matter when someone types one back in."""
    return "".join(ch for ch in str(code or "").lower() if ch.isalnum())


def hash_recovery_code(code):
    """A fast hash is right here, unlike for a password.

    These codes are random rather than chosen, so there is no dictionary to run
    against them. What the hash buys is that a copy of the database does not
    hand over working codes.
    """
    return hashlib.sha256(normalise_recovery_code(code).encode()).hexdigest()


# ---------------------------------------------------------------- pending sign-in


def _password_fingerprint(user):
    return hashlib.sha256(user.password.encode()).hexdigest()[:20]


def pending_token(user):
    """Proof that this person got the password right -- and nothing more.

    It is not a session: it opens no part of the API, only the two-step
    endpoints. It is tied to the current password hash, so changing or
    resetting the password voids any half-finished sign-in along with it.
    """
    return signing.dumps(
        {"uid": user.pk, "pw": _password_fingerprint(user)}, salt=PENDING_SALT, compress=True
    )


def user_from_pending(token):
    """The account a pending token was issued to, or None if it is no longer good."""
    from .models import User

    try:
        data = signing.loads(str(token or ""), salt=PENDING_SALT, max_age=PENDING_MAX_AGE)
    except signing.BadSignature:  # SignatureExpired is a subclass
        return None

    user = User.objects.filter(pk=data.get("uid"), is_active=True).first()
    if user is None or not hmac.compare_digest(_password_fingerprint(user), str(data.get("pw", ""))):
        return None
    return user


def pending_user_id(token):
    """The account a pending token names, ignoring expiry. For rate limiting only."""
    try:
        return signing.loads(str(token or ""), salt=PENDING_SALT).get("uid")
    except signing.BadSignature:
        return None


def has_confirmed_device(user):
    """Whether this account has a working authenticator -- a fresh query, never
    a cached relation, because the login and refresh checks must see a reset
    the moment it happens."""
    from .models import MfaDevice

    return (
        MfaDevice.objects.filter(user=user, confirmed_at__isnull=False).exclude(secret="").exists()
    )


def required_for(user):
    """Whether this account has to use two-step sign-in.

    Everyone, by default. A single setting rather than a per-role rule, so the
    policy is one line to change and cannot drift between the login view, the
    refresh view and the screens that explain it.
    """
    return bool(getattr(settings, "MFA_REQUIRED", True))
