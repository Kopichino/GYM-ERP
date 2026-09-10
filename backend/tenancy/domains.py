"""Proving a gym owns the domain it is claiming, and routing by it.

The claim is proved with a DNS TXT record, because publishing one requires
control of the domain and nothing else does. Without that step anybody could
add `app.a-rival-gym.com` here -- and since the tenant is resolved *from* the
hostname, a spoofed claim would not merely be untidy, it would be a route into
another gym's data.

Verification is therefore the gate, not a formality: an unverified row is
ignored by `tenant_from_host` entirely.

TLS is deliberately not managed here. On Render and Vercel the host issues the
certificate once the domain points at it; this module records what the host
reports rather than pretending to hold private keys.
"""

import logging

from django.utils import timezone

logger = logging.getLogger(__name__)

#: Where the gym publishes the token. A dedicated subdomain rather than a TXT
#: on the apex, so the record cannot collide with SPF or anything else already
#: living there -- adding a second apex TXT is a common way to break email.
TXT_PREFIX = "_ironcore-verify"

#: How long to wait on a resolver before giving up. DNS is usually instant and
#: occasionally hangs; an admin clicking "Verify" should get an answer either
#: way rather than a spinner.
DNS_TIMEOUT_SECONDS = 5


class VerificationError(Exception):
    """The domain could not be verified, with a reason to show the owner."""


def expected_record(domain):
    """The exact record the gym has to create, ready to be shown verbatim.

    Returned as data rather than a formatted sentence because the admin screen
    renders it as a copyable row -- an owner pasting this into their registrar
    should not have to pick the parts out of prose.
    """
    return {
        "type": "TXT",
        "name": f"{TXT_PREFIX}.{domain.hostname}",
        "value": domain.verification_token,
    }


def _txt_values(name):
    """Every TXT string published at `name`. Raises VerificationError on failure."""
    import dns.exception
    import dns.resolver

    resolver = dns.resolver.Resolver()
    resolver.timeout = DNS_TIMEOUT_SECONDS
    resolver.lifetime = DNS_TIMEOUT_SECONDS

    try:
        answer = resolver.resolve(name, "TXT")
    except dns.resolver.NXDOMAIN:
        raise VerificationError(
            f"No TXT record found at {name}. It can take a few minutes to "
            "appear after you add it."
        )
    except dns.resolver.NoAnswer:
        raise VerificationError(f"{name} exists but has no TXT record on it.")
    except dns.exception.Timeout:
        raise VerificationError(
            "The DNS lookup timed out. That is usually temporary -- try again "
            "in a minute."
        )
    except dns.exception.DNSException as exc:
        logger.warning("DNS lookup failed for %s: %s", name, exc)
        raise VerificationError("Could not read DNS for that domain.")

    values = []
    for record in answer:
        # A TXT record is a list of strings, and long values arrive split. The
        # parts are concatenated with nothing between them, which is what the
        # spec says and what every registrar does when a value exceeds 255
        # characters.
        parts = [
            part.decode() if isinstance(part, bytes) else str(part)
            for part in record.strings
        ]
        values.append("".join(parts))
    return values


def verify(domain, now=None):
    """Check the TXT record and mark the domain verified if it matches.

    Idempotent: verifying an already-verified domain re-checks and leaves the
    original timestamp alone, so a re-run does not make an old domain look
    freshly proved.
    """
    now = now or timezone.now()
    record = expected_record(domain)

    try:
        values = _txt_values(record["name"])
    except VerificationError as exc:
        domain.last_checked_at = now
        domain.last_error = str(exc)[:200]
        domain.save(update_fields=["last_checked_at", "last_error"])
        raise

    if record["value"] not in values:
        domain.last_checked_at = now
        # Says what was found, because "verification failed" with a correct-
        # looking record on screen is the most frustrating possible message --
        # usually the registrar added a suffix or the old value is still cached.
        found = ", ".join(values[:3]) or "nothing"
        domain.last_error = f"Found {found} at that name, not the token."[:200]
        domain.save(update_fields=["last_checked_at", "last_error"])
        raise VerificationError(domain.last_error)

    domain.last_checked_at = now
    domain.last_error = ""
    if domain.verified_at is None:
        domain.verified_at = now
    domain.save(update_fields=["verified_at", "last_checked_at", "last_error"])
    return domain
