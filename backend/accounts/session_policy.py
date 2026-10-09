"""How long each kind of sign-in lasts, and the rules that keep it finite.

Three kinds of session share the one refresh-token mechanism and differ only in
their ceiling, counted from the moment of login:

    normal    the default; what signing in has always meant
    remember  "Remember me": stay signed in for longer
    trusted   "Trust this device": this browser is a known device, for longest

The ceilings are settings (`AUTH_SESSION_MAX_AGE`, `AUTH_REMEMBER_ME_MAX_AGE`,
`AUTH_TRUSTED_DEVICE_MAX_AGE`) so a deployment can tighten or loosen them without
a code change -- and they are *validated*, because the failure to guard against is
a typo turning "90 days" into "never": a duration that is zero, negative, shorter
than is useful, longer than a year, or out of order is refused at boot and again
whenever a session is opened, rather than quietly accepted.

This module imports nothing from Django's models, so `settings.py` can use it
while the settings are still being built.
"""

from datetime import timedelta

from django.core.exceptions import ImproperlyConfigured

NORMAL = "normal"
REMEMBER = "remember"
TRUSTED = "trusted"
KINDS = (NORMAL, REMEMBER, TRUSTED)

#: The setting that holds each kind's ceiling.
SETTING_FOR = {
    NORMAL: "AUTH_SESSION_MAX_AGE",
    REMEMBER: "AUTH_REMEMBER_ME_MAX_AGE",
    TRUSTED: "AUTH_TRUSTED_DEVICE_MAX_AGE",
}

#: Shorter than this is not a session worth the name: the access token alone
#: lasts a quarter of it.
MIN_LIFETIME = timedelta(hours=1)
#: The longest any session may last. A year is already generous; anything beyond
#: it is, in practice, permanent, and a permanent login is not what was asked for.
MAX_LIFETIME = timedelta(days=365)


def validate_lifetimes(session, remember, trusted):
    """Raise `ImproperlyConfigured` unless the three ceilings are safe and in order."""
    named = (
        (SETTING_FOR[NORMAL], session),
        (SETTING_FOR[REMEMBER], remember),
        (SETTING_FOR[TRUSTED], trusted),
    )
    for name, value in named:
        if not isinstance(value, timedelta):
            raise ImproperlyConfigured(f"{name} must be a duration, not {value!r}.")
        if value < MIN_LIFETIME:
            raise ImproperlyConfigured(
                f"{name} is {value}, which is shorter than the {MIN_LIFETIME} minimum "
                "(zero and negative values are not allowed)."
            )
        if value > MAX_LIFETIME:
            raise ImproperlyConfigured(
                f"{name} is {value}, longer than the {MAX_LIFETIME.days}-day maximum. "
                "A session that long is effectively permanent."
            )
    if not session <= remember <= trusted:
        raise ImproperlyConfigured(
            "Session lifetimes must satisfy AUTH_SESSION_MAX_AGE <= AUTH_REMEMBER_ME_MAX_AGE "
            f"<= AUTH_TRUSTED_DEVICE_MAX_AGE; got {session}, {remember}, {trusted}."
        )


def max_age_for(kind):
    """The ceiling for a session of `kind`, from the settings as they are now.

    Read -- and validated -- every time a session is opened, not once at import,
    so a setting changed afterwards takes effect, and an unsafe one is refused
    wherever it came from.
    """
    from django.conf import settings

    if kind not in SETTING_FOR:
        raise ValueError(f"Unknown session kind {kind!r}.")
    validate_lifetimes(
        settings.AUTH_SESSION_MAX_AGE,
        settings.AUTH_REMEMBER_ME_MAX_AGE,
        settings.AUTH_TRUSTED_DEVICE_MAX_AGE,
    )
    return getattr(settings, SETTING_FOR[kind])
