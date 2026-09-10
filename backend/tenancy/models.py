"""Who owns what, on a platform running many gyms.

Two levels, because a gym chain needs both:

* `Organisation` is the brand. It owns the things that must not be maintained
  three times over -- the price list, the badge ladders, the identity on the
  door. A gym with three branches has one of these.
* `Tenant` is a branch. It owns everything operational: visits, payments,
  staff, invoices. Isolation is at this level, because "who came to the gym
  yesterday" is a question about a building, not a brand.

`Membership` is what connects a person to a branch, and it is deliberately not
a column on `User`. A trainer can work at two unrelated gyms; an owner oversees
three branches of their own; a member may hold a pass at a gym near work and
another near home. A `role` field on the user cannot express any of that -- it
would have to pick one answer for a question whose answer depends on which
building the person is standing in.
"""

import hashlib
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from accounts.models import Role

from .managers import TenantManager, UnscopedManager


class Organisation(models.Model):
    """A gym brand, owning one or more branches.

    Shared configuration hangs off this rather than off each branch, so a chain
    changing its price list changes it once. Every organisation has at least one
    tenant; a single-site gym is simply an organisation with one branch, which
    keeps one code path rather than special-casing the common case.
    """

    name = models.CharField(max_length=120)
    slug = models.SlugField(
        max_length=60,
        unique=True,
        help_text="Stable id used in URLs and support tooling.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Tenant(models.Model):
    """One branch: the unit of data isolation.

    Every operational row in the system carries one of these. The slug is
    globally unique rather than unique per organisation because it appears in
    `/t/<slug>/` today and becomes a hostname later, and both of those are
    global namespaces -- two branches called "central" at different gyms would
    collide the moment either got a domain.
    """

    organisation = models.ForeignKey(
        Organisation, on_delete=models.PROTECT, related_name="tenants"
    )
    name = models.CharField(max_length=120)
    slug = models.SlugField(
        max_length=60,
        unique=True,
        help_text="Appears in /t/<slug>/ and later maps to a custom domain.",
    )
    # Where this branch actually is. Branding (name, logo, colours) lives on the
    # organisation; the things that genuinely differ per building live here.
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    # Its own GSTIN when the branch files separately, which is also why invoice
    # numbering is sequenced per tenant rather than per organisation.
    gstin = models.CharField(max_length=20, blank=True)
    state = models.CharField(max_length=60, blank=True)
    # Short code that prefixes this branch's invoice numbers, e.g. "FIT" giving
    # FIT/2025-26/0001. Kept separate from the slug: a slug is a URL and may be
    # renamed, while an invoice prefix is printed on a statutory document and
    # must not move once anything has been issued.
    invoice_prefix = models.CharField(
        max_length=8,
        blank=True,
        help_text="Prefixes invoice numbers, e.g. FIT in FIT/2025-26/0001.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["organisation__name", "name"]

    def __str__(self):
        return f"{self.organisation.name} - {self.name}"


class Membership(models.Model):
    """One person's standing at one branch, in one role.

    Multiple rows per (user, tenant) on purpose: a trainer who also trains at
    their own gym holds both `trainer` and `member` there, and the codebase
    already assumes that is possible -- the PT diary filters on
    `Q(trainer=user) | Q(member=user)`. Collapsing role to one value per branch
    would make that pair unrepresentable.

    `expires_on` governs **access to the branch** and nothing else. Whether a
    member's subscription is paid up stays derived from the payment ledger, as
    it always has been. Two fields answering "is this person active?" is exactly
    the disagreement this codebase is built to avoid, so they answer different
    questions: this one is "may they be scoped into this tenant at all", not
    "have they paid".
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships"
    )
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField(max_length=10, choices=Role.choices)
    starts_on = models.DateField(default=timezone.localdate)
    # Null means open-ended, which is the normal case for staff and for a
    # subscribing member. A dated one is how a day-pass guest who wants their
    # visit history, or a trainer on a fixed contract, is represented.
    expires_on = models.DateField(null=True, blank=True)
    # Kept separate from expiry so access can be revoked immediately without
    # rewriting a date that means something else.
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["tenant", "user", "role"]
        indexes = [models.Index(fields=["user", "is_active"])]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "tenant", "role"],
                name="one_membership_per_user_tenant_role",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(expires_on__isnull=True)
                    | models.Q(expires_on__gte=models.F("starts_on"))
                ),
                name="membership_does_not_expire_before_it_starts",
            ),
        ]

    def is_current(self, on=None):
        """Whether this membership grants access on `on` (default today)."""
        on = on or timezone.localdate()
        if not self.is_active or self.starts_on > on:
            return False
        return self.expires_on is None or self.expires_on >= on

    def __str__(self):
        return f"{self.user} @ {self.tenant} ({self.get_role_display()})"


def _new_verification_token():
    """A token the gym publishes in DNS to prove they own the domain."""
    return secrets.token_urlsafe(24)


class Domain(models.Model):
    """A hostname that serves one gym.

    Ownership is proved before the domain does anything, and the proof is a TXT
    record only someone with control of the domain can publish. Skipping that
    step would let anyone claim `app.a-competitor.com` and have this platform
    answer for it -- and because the host resolves the tenant *from* the
    hostname, a spoofed claim would be a route into another gym's data.

    So an unverified row is inert: `tenant_from_host` ignores it entirely. It
    exists only to hold the token while the owner goes and creates the record.

    TLS is not issued here. On Render and Vercel the certificate is the host's
    job once the domain points at them, so `certificate` records what the host
    reported rather than pretending this system manages keys.
    """

    class Certificate(models.TextChoices):
        PENDING = "pending", "Not requested yet"
        ISSUING = "issuing", "Host is issuing"
        ACTIVE = "active", "Live"
        FAILED = "failed", "Failed - see the host"

    tenant = models.ForeignKey(
        "tenancy.Tenant", on_delete=models.CASCADE, related_name="domains"
    )
    #: Stored lowercase; hostnames are case-insensitive and a mixed-case row
    #: would never match an incoming request.
    hostname = models.CharField(max_length=253, unique=True)
    verification_token = models.CharField(
        max_length=64, default=_new_verification_token, editable=False
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    #: The one used to build links in email. A gym may keep an old domain
    #: serving after a rename, but only one is the address it advertises.
    is_primary = models.BooleanField(default=False)
    certificate = models.CharField(
        max_length=10, choices=Certificate.choices, default=Certificate.PENDING
    )
    last_checked_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    #: Scoped so a gym manages only its own domains. Resolution reads through
    #: `.unscoped` by necessity -- working out *which* tenant a request is for
    #: happens before there is one in scope, so the lookup cannot be filtered
    #: by the answer it is trying to find.
    tenant_field = "tenant"
    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        ordering = ["-is_primary", "hostname"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant"],
                condition=models.Q(is_primary=True),
                name="one_primary_domain_per_tenant",
            ),
        ]

    @property
    def is_verified(self):
        return self.verified_at is not None

    def save(self, *args, **kwargs):
        self.hostname = self.hostname.strip().lower().rstrip(".")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.hostname} -> {self.tenant.slug}"


class SendingDomain(models.Model):
    """The domain a gym's outgoing email is sent from.

    Separate from `Domain` on purpose. A gym is very likely to serve its portal
    at `app.theirgym.com` while sending mail as `theirgym.com` -- the web
    address is a subdomain you point at a host, the sending domain is the one
    in the From header, and forcing them to be the same row would make the
    common case impossible to express.

    Proving it takes more than one record. SPF says this sender may use the
    domain, DKIM signs the message, and a return-path CNAME makes bounces come
    back somewhere useful. All three come *from the provider* -- the DKIM public
    key is generated per domain and cannot be invented here -- so an install
    with no provider configured can hold the row but not the records.

    Until every part verifies, mail keeps going out from the platform address.
    A half-configured sending domain is worse than none: a From header the
    receiving server cannot authenticate lands in spam, and the gym would never
    know their reminders had stopped arriving.
    """

    tenant = models.OneToOneField(
        "tenancy.Tenant", on_delete=models.CASCADE, related_name="sending_domain"
    )
    domain = models.CharField(max_length=253)
    #: What members see in the From header, e.g. "no-reply". Kept apart from the
    #: domain so a gym can change one without re-verifying the other.
    from_local_part = models.CharField(max_length=64, default="no-reply")
    from_name = models.CharField(
        max_length=80, blank=True,
        help_text="The name beside the address. Defaults to the gym's name.",
    )

    #: Supplied by the provider; blank until the domain is registered with them.
    dkim_selector = models.CharField(max_length=64, blank=True)
    dkim_value = models.TextField(blank=True)
    return_path_cname = models.CharField(max_length=253, blank=True)

    spf_verified = models.BooleanField(default=False)
    dkim_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    tenant_field = "tenant"
    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        ordering = ["domain"]

    @property
    def is_verified(self):
        """Both halves, not either. SPF alone still fails DMARC alignment."""
        return self.spf_verified and self.dkim_verified

    @property
    def from_email(self):
        return f"{self.from_local_part}@{self.domain}"

    def save(self, *args, **kwargs):
        self.domain = self.domain.strip().lower().rstrip(".")
        self.from_local_part = self.from_local_part.strip().lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.from_email} ({self.tenant.slug})"


def generate_lead_key():
    """Returns (plaintext, hash). Only the hash is stored, as with device keys."""
    raw = "lead_" + secrets.token_urlsafe(28)
    return raw, hash_lead_key(raw)


def hash_lead_key(raw):
    return hashlib.sha256(raw.encode()).hexdigest()


class LeadFailure(models.TextChoices):
    """Why a website submission was turned away.

    Stored as a code rather than a sentence so the screen can pair each one
    with advice the owner can act on -- "your site is still using a key you
    revoked" needs a different next step from "your form is missing a field".
    """

    REVOKED = "revoked", "The key has been revoked"
    ORIGIN = "origin", "Blocked by the allowed-addresses list"
    SUSPENDED = "suspended", "The gym is not accepting enquiries"
    PAYLOAD = "payload", "The form did not send a name and contact"
    RATE = "rate", "Too many submissions in one hour"


class LeadApiKey(models.Model):
    """Lets a gym's own website post enquiries straight into their pipeline.

    **This key is not a secret and the design must not pretend otherwise.** It
    goes in a contact form on a public marketing site, which usually means it
    ends up in client-side JavaScript where anyone can read it. Everything here
    follows from that:

    * it can *create* a lead and do nothing else -- no reading, no listing, no
      access to anything already in the pipeline;
    * it is rate limited per key, so a leaked one is a nuisance rather than an
      outage, and one gym's flood cannot exhaust another gym's allowance;
    * it is revocable in one click, and a gym can hold several so a compromised
      one can be replaced without taking the working form down first.

    Stored as a hash for the same reason a password is: a database dump should
    not hand someone every gym's key. The plaintext is shown once.
    """

    tenant = models.ForeignKey(
        "tenancy.Tenant", on_delete=models.CASCADE, related_name="lead_keys"
    )
    #: Which site this belongs to, so an owner can tell two keys apart when
    #: deciding which to revoke.
    label = models.CharField(max_length=80, help_text="Where this key is used.")
    key_hash = models.CharField(max_length=64, unique=True)
    #: Optional. When set, requests must come from one of these origins -- which
    #: turns a leaked key into something that only works from the gym's own
    #: site. Not required, because a form posted server-side sends no Origin.
    allowed_origins = models.TextField(
        blank=True, help_text="One origin per line, e.g. https://www.yourgym.com"
    )
    is_active = models.BooleanField(default=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    leads_created = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    #: Why the last refused submission was refused, and when.
    #:
    #: A form that breaks on someone else's website breaks *silently* from here:
    #: the visitor sees an apology, and the gym sees nothing at all until they
    #: notice enquiries have dried up, which takes weeks. These three fields are
    #: what lets the admin screen say so on the day it happens.
    #:
    #: Only refusals this system can actually attribute to a key are counted --
    #: a wrong key, a blocked origin, a malformed form, a rate limit. A gym's
    #: site being down, or unable to reach us at all, never arrives here and
    #: cannot be reported.
    last_failure_at = models.DateTimeField(null=True, blank=True)
    last_failure_reason = models.CharField(
        max_length=20, blank=True, choices=LeadFailure.choices
    )
    #: Reset to zero by any accepted lead, so a fixed form stops warning on its
    #: own rather than needing someone to dismiss it. Recording is debounced
    #: (see `record_failure`), so this counts *bursts* of failure rather than
    #: individual requests -- thirty people meeting one broken form in a minute
    #: is one problem, not thirty.
    failures_since_success = models.PositiveIntegerField(default=0)

    tenant_field = "tenant"
    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        ordering = ["-created_at"]

    def origins(self):
        return [line.strip().rstrip("/") for line in self.allowed_origins.splitlines() if line.strip()]

    def allows(self, origin):
        """Whether a request from `origin` may use this key.

        No configured origins means no restriction -- a server-side form post
        carries no Origin header at all, and refusing those would break the
        commonest integration.
        """
        allowed = self.origins()
        if not allowed:
            return True
        if not origin:
            return False
        return origin.rstrip("/") in allowed

    def __str__(self):
        return f"{self.label} ({self.tenant.slug})"
