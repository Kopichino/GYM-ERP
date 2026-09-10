"""Which address a gym's mail goes out from, and proving they may use it.

Two senders exist on this platform and they must never be confused:

* **A gym's identity** -- reminders and invoices to *their* members, from their
  own domain, so a member sees the gym they joined rather than a name they have
  never heard of.
* **The platform identity** -- billing, support and service notices to gym
  *owners*. Fixed, never tenant-branded. A message telling an owner their
  subscription lapsed must not arrive dressed as their own gym; it is from us,
  and dressing it otherwise is how a legitimate mail looks like a forgery.

`platform_sender()` and `sender_for()` are the only two ways to pick a From
address, and nothing else should build one.

**Why Postmark over SendGrid.** Both work. Postmark wins here on the two things
this phase actually needs: its DNS onboarding returns the exact records to
publish and reports per-record verification state through the API, which is
what makes a guided setup possible rather than "go and read their docs"; and it
is transactional-only, so a gym's renewal reminders are not sharing reputation
with bulk marketing traffic. SendGrid is the better choice if you later want
campaigns from the same account -- it is not what this is for.
"""

import logging

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

DNS_TIMEOUT_SECONDS = 5


class SendingSetupError(Exception):
    """A sending domain could not be set up or verified, with a reason."""


def platform_sender():
    """The address the platform writes to gym owners from.

    Deliberately not derived from any tenant, and deliberately not the same
    setting as `DEFAULT_FROM_EMAIL`: that one is a fallback for member mail on
    an install with no sending domain, and the two drifting into each other is
    exactly the confusion this function exists to prevent.
    """
    return (
        getattr(settings, "PLATFORM_FROM_EMAIL", "")
        or getattr(settings, "DEFAULT_FROM_EMAIL", "")
    )


def sender_for(tenant):
    """The From address for mail to `tenant`'s members.

    Falls back to the platform address when the gym has no verified sending
    domain. Sending as an unverified domain is worse than not trying: the
    receiving server cannot authenticate it, the mail lands in spam, and the
    gym never learns their reminders stopped arriving.
    """
    identity = getattr(tenant, "sending_domain", None) if tenant else None
    if identity is None or not identity.is_verified:
        return platform_sender()

    name = identity.from_name or getattr(tenant, "name", "") or ""
    return f"{name} <{identity.from_email}>" if name else identity.from_email


# --------------------------------------------------------------- DNS checking

def _txt_values(name):
    import dns.exception
    import dns.resolver

    resolver = dns.resolver.Resolver()
    resolver.timeout = DNS_TIMEOUT_SECONDS
    resolver.lifetime = DNS_TIMEOUT_SECONDS
    try:
        answer = resolver.resolve(name, "TXT")
    except dns.exception.DNSException:
        return []
    values = []
    for record in answer:
        parts = [
            part.decode() if isinstance(part, bytes) else str(part)
            for part in record.strings
        ]
        values.append("".join(parts))
    return values


def _cname_target(name):
    import dns.exception
    import dns.resolver

    resolver = dns.resolver.Resolver()
    resolver.timeout = DNS_TIMEOUT_SECONDS
    resolver.lifetime = DNS_TIMEOUT_SECONDS
    try:
        answer = resolver.resolve(name, "CNAME")
    except dns.exception.DNSException:
        return None
    return str(answer[0].target).rstrip(".").lower()


def spf_ok(domain, include=None):
    """Whether the domain's SPF authorises our provider.

    Checks the *include* rather than the whole string matching, because a gym
    almost always has an SPF record already -- for their own mail, for their
    accountant's invoicing tool -- and the correct action is to add one term to
    it, not replace it. Demanding an exact value would tell owners to break
    their existing email.
    """
    include = include or getattr(settings, "EMAIL_SPF_INCLUDE", "spf.mtasv.net")
    for value in _txt_values(domain):
        if value.lower().startswith("v=spf1") and include.lower() in value.lower():
            return True
    return False


def dkim_ok(identity):
    """Whether the DKIM record the provider issued is published.

    Providers publish DKIM either as a TXT holding the public key or as a CNAME
    pointing at a record they host. Both are normal, so both are accepted --
    insisting on one would fail a correctly configured domain.
    """
    if not identity.dkim_selector:
        return False

    name = f"{identity.dkim_selector}._domainkey.{identity.domain}"

    if identity.dkim_value:
        wanted = identity.dkim_value.strip()
        for value in _txt_values(name):
            # Compared with whitespace removed: registrars wrap long keys and
            # the reassembled string often differs from the original only by
            # spaces, which would otherwise read as a mismatch.
            if "".join(wanted.split()) in "".join(value.split()):
                return True

    target = _cname_target(name)
    if target and identity.return_path_cname:
        return True
    return bool(target)


def verify(identity, now=None):
    """Re-check both records and update the identity. Returns it.

    Never raises for a record simply not being there yet -- that is the normal
    state during setup, and the caller shows what is still outstanding.
    """
    now = now or timezone.now()
    identity.spf_verified = spf_ok(identity.domain)
    identity.dkim_verified = dkim_ok(identity)
    identity.last_checked_at = now

    if identity.is_verified:
        identity.last_error = ""
        if identity.verified_at is None:
            identity.verified_at = now
    else:
        missing = []
        if not identity.spf_verified:
            missing.append("SPF")
        if not identity.dkim_verified:
            missing.append("DKIM")
        identity.last_error = (
            f"Still waiting on {' and '.join(missing)}. DNS changes can take "
            "a few minutes to appear."
        )[:300]

    identity.save(
        update_fields=[
            "spf_verified", "dkim_verified", "verified_at",
            "last_checked_at", "last_error",
        ]
    )
    return identity
