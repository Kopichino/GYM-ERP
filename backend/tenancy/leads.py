"""The public endpoint a gym's own website posts enquiries to.

This is the only unauthenticated write path in the system, so it is built on
the assumption that its key is public. A contact form on a marketing site puts
the key in client-side JavaScript, where anybody can read it -- treating it as
a secret would be a comfortable fiction, and every defence here exists because
it is not one.

What protects the pipeline is therefore not the key's secrecy but its narrow
reach: it can create one enquiry and do nothing else. It cannot read the
pipeline, cannot list what is already there, cannot see a member. The worst a
leaked key does is put junk in one gym's enquiry list, which an owner can stop
by revoking it.

Three layers on top of that:

* **Rate limiting per key**, not per IP. A gym's form is behind their CDN, so
  every visitor may share an address -- and IP limiting would let one gym's
  spam exhaust every other gym's allowance, which is the exact cross-tenant
  coupling the rest of this platform is built to avoid.
* **A honeypot field** that real people never fill in. Cheap, and it catches
  the undirected form-filling bots that make up most of this traffic.
* **Optional origin pinning**, so a gym can tie their key to their own site.
"""

import logging

from django.db import models
from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed, Throttled
from rest_framework.permissions import BasePermission
from rest_framework.throttling import SimpleRateThrottle

from .models import LeadApiKey, LeadFailure, hash_lead_key

logger = logging.getLogger(__name__)

HEADER = "HTTP_X_LEAD_KEY"

#: The field a bot fills and a person cannot see. Named as something a form
#: filler would plausibly complete, because a field called "honeypot" is one
#: any competent scraper skips.
HONEYPOT_FIELD = "company_website"


class LeadKeyAuthentication(BaseAuthentication):
    """Identifies the gym by its lead key.

    Like the device key, this deliberately does not populate `request.user`: a
    website is not a person, and letting it act as one would hand a public key
    whatever permissions that user has. The key is attached as
    `request.lead_key` and only this endpoint looks at it.
    """

    def authenticate(self, request):
        raw = request.META.get(HEADER)
        if not raw:
            return None

        key = LeadApiKey.unscoped.filter(
            key_hash=hash_lead_key(raw)
        ).select_related("tenant").first()

        if key is None:
            # Nothing to attribute this to -- an unknown key belongs to no gym,
            # so there is no screen it could be reported on.
            raise AuthenticationFailed("Unknown lead key.")
        if not key.is_active:
            # Worth recording even though the owner did the revoking: it means
            # their website is still pointing at the old key and every enquiry
            # since is being lost.
            record_failure(key, LeadFailure.REVOKED)
            raise AuthenticationFailed("This key has been revoked.")
        if not key.tenant.is_active:
            record_failure(key, LeadFailure.SUSPENDED)
            raise AuthenticationFailed("That gym is not accepting enquiries.")

        origin = request.META.get("HTTP_ORIGIN", "")
        if not key.allows(origin):
            # Named plainly: an owner who pinned their origin and then moved
            # the form to a new domain would otherwise get an unexplained
            # refusal from a key that looks correct.
            record_failure(key, LeadFailure.ORIGIN)
            raise AuthenticationFailed(
                "This key is restricted to a different website address."
            )

        request.lead_key = key
        return None

    def authenticate_header(self, request):
        # Without this DRF turns a bad key into a 403, telling the caller they
        # are forbidden rather than unauthenticated -- and hiding that rotating
        # the key is what fixes it.
        return "X-Lead-Key"


class IsLeadKey(BasePermission):
    message = "A valid X-Lead-Key header is required."

    def has_permission(self, request, view):
        return getattr(request, "lead_key", None) is not None


class LeadRateThrottle(SimpleRateThrottle):
    """Per key, so one gym's flood cannot spend another gym's allowance.

    Falls back to the IP when there is no key -- an unauthenticated caller
    hammering the endpoint still needs limiting, it just cannot be attributed
    to a gym.
    """

    scope = "leads"

    def get_cache_key(self, request, view):
        key = getattr(request, "lead_key", None)
        ident = f"key:{key.pk}" if key else f"ip:{self.get_ident(request)}"
        return self.cache_format % {"scope": self.scope, "ident": ident}

    def throttle_failure(self):
        # Recorded here rather than in the view because a throttled request
        # never reaches one. A gym whose form is being hammered has a problem
        # worth seeing, whether it is a bot or a genuinely popular campaign.
        record_failure(getattr(self._request, "lead_key", None), LeadFailure.RATE)
        return super().throttle_failure()

    def allow_request(self, request, view):
        # `throttle_failure` takes no request, so stash it on the way past.
        self._request = request
        return super().allow_request(request, view)


def looks_like_spam(payload):
    """Whether this submission should be dropped without comment.

    Returns a reason for the log, or None. Bots are not told which check caught
    them -- an error explaining the honeypot is a free lesson in bypassing it.
    """
    if str(payload.get(HONEYPOT_FIELD, "")).strip():
        return "honeypot filled"

    name = str(payload.get("name", "")).strip()
    if len(name) > 150:
        return "implausible name length"

    # A message that is mostly links is the shape of the link-spam that arrives
    # at every public form; a genuine enquiry rarely contains any.
    message = str(payload.get("message", ""))
    if message.count("http") >= 3:
        return "link spam"
    return None


def record_use(key, created):
    """Keep a light usage trail, so an owner can see a key is actually working."""
    values = {"last_used_at": timezone.now()}
    if created:
        # Anything that reached the pipeline clears the alarm. A form that has
        # been fixed stops warning by itself, which matters more than it looks:
        # a warning that needs dismissing gets dismissed out of habit, and then
        # the next real fault is dismissed too.
        values["leads_created"] = models.F("leads_created") + 1
        values["failures_since_success"] = 0
    LeadApiKey.unscoped.filter(pk=key.pk).update(**values)


#: How long one burst of failures is treated as a single event.
#:
#: Without this, every refused request is a database write, and the refusals
#: that happen *before* the rate limit -- a revoked key, a blocked origin --
#: are unbounded. Anyone holding a scraped key could turn a public endpoint
#: into a write amplifier. Coalescing also makes the count more honest: thirty
#: visitors meeting one broken form in a minute is one fault, not thirty.
FAILURE_DEBOUNCE_SECONDS = 60


def record_failure(key, reason):
    """Note that a submission was turned away, so the gym can be told.

    Debounced per key *and* reason: a repeat of the same fault within the
    window is the same fault. A different reason writes immediately, because a
    key that starts failing for a new reason has genuinely changed state and
    the screen should say the current thing rather than the stale one.
    """
    if key is None:
        return

    now = timezone.now()
    recent = (
        key.last_failure_at is not None
        and key.last_failure_reason == reason
        and (now - key.last_failure_at).total_seconds() < FAILURE_DEBOUNCE_SECONDS
    )
    if recent:
        return

    LeadApiKey.unscoped.filter(pk=key.pk).update(
        last_failure_at=now,
        last_failure_reason=reason,
        failures_since_success=models.F("failures_since_success") + 1,
    )
    logger.info(
        "Website form refused for %s: %s", key.tenant.slug, reason
    )


def throttled_response_seconds(exc):
    return getattr(exc, "wait", None) if isinstance(exc, Throttled) else None
