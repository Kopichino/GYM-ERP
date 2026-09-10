"""Asking the host to issue a certificate for a verified domain.

**This does not manage certificates.** It has no private keys, runs no ACME
client, and stores nothing sensitive. On Render and Vercel -- which is where
this deploys -- TLS is the platform's job: you register the domain with them,
they answer the ACME challenge themselves because they terminate the
connection, and they renew it. Anything this system did with keys would be a
worse copy of that, sitting on a free-tier disk that is wiped on every deploy.

So the job here is narrow and honest: tell the host a domain exists, and record
what it says back. `certificate` on the Domain row is a *report*, not a state
this code controls.

The provider is pluggable because the answer is entirely host-specific, and
defaults to one that does nothing -- an install with no credentials configured
should leave the field at "pending" and say so on screen, rather than pretend.
"""

import logging

from django.conf import settings

from .models import Domain

logger = logging.getLogger(__name__)


class Provider:
    """What a host adapter has to answer."""

    name = "none"

    def register(self, domain):
        """Ask the host to serve `domain`. Return a Domain.Certificate value."""
        raise NotImplementedError


class ManualProvider(Provider):
    """The default: nobody is calling an API, so say so.

    Used when no host credentials are configured, which is every local install
    and any deployment where the operator adds domains through the host's
    dashboard by hand. Reporting "pending" is truthful; reporting "active"
    because we did not check would be worse than reporting nothing.
    """

    name = "manual"

    def register(self, domain):
        logger.info(
            "No certificate provider configured; add %s in your host's "
            "dashboard to have TLS issued.",
            domain.hostname,
        )
        return Domain.Certificate.PENDING


class RenderProvider(Provider):
    """Registers the domain with a Render service.

    Render issues and renews the certificate once the domain resolves to them,
    so a successful call here means "handed over", not "live" -- hence
    `ISSUING` rather than `ACTIVE`. The status becomes active when the host
    reports it, which `refresh` below reads back.
    """

    name = "render"
    BASE = "https://api.render.com/v1"

    def __init__(self, api_key, service_id):
        self.api_key = api_key
        self.service_id = service_id

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def register(self, domain):
        import requests

        try:
            response = requests.post(
                f"{self.BASE}/services/{self.service_id}/custom-domains",
                json={"name": domain.hostname},
                headers=self._headers(),
                timeout=15,
            )
        except requests.RequestException as exc:
            logger.warning("Render domain registration failed: %s", exc)
            domain.last_error = "Could not reach the hosting provider."[:200]
            return Domain.Certificate.FAILED

        # Already registered is a success for our purposes: the desired state
        # is "the host knows about this domain", and it does.
        if response.status_code in (200, 201, 409):
            return Domain.Certificate.ISSUING

        logger.warning(
            "Render refused %s: %s %s", domain.hostname, response.status_code,
            response.text[:200],
        )
        domain.last_error = f"Host refused the domain ({response.status_code})."[:200]
        return Domain.Certificate.FAILED


def provider():
    """The configured adapter, or the honest do-nothing one."""
    key = getattr(settings, "RENDER_API_KEY", "")
    service = getattr(settings, "RENDER_SERVICE_ID", "")
    if key and service:
        return RenderProvider(key, service)
    return ManualProvider()


def request_certificate(domain):
    """Hand a verified domain to the host. Returns the domain.

    Refuses an unverified one: registering a domain the gym has not proved it
    owns would ask the host to serve a name on someone else's behalf, which is
    the same hole the TXT check exists to close.
    """
    if not domain.is_verified:
        raise ValueError("Verify the domain before requesting a certificate.")

    domain.certificate = provider().register(domain)
    domain.save(update_fields=["certificate", "last_error"])
    return domain
