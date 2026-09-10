from django.conf import settings
from django.db import models

from tenancy.managers import TenantManager, UnscopedManager
from django.utils import timezone


class EnquiryStatus(models.TextChoices):
    OPEN = "open", "To call"
    CONTACTED = "contacted", "Contacted"
    TRIAL = "trial", "Trial booked"
    JOINED = "joined", "Joined"
    LOST = "lost", "Not interested"


class EnquirySource(models.TextChoices):
    """Where the lead came from. Worth a column of its own rather than a note,
    because "which channel actually converts" is the one question the front
    desk's spend depends on, and you cannot group by free text."""

    WALK_IN = "walk_in", "Walked in"
    PHONE = "phone", "Phone call"
    INSTAGRAM = "instagram", "Instagram"
    FACEBOOK = "facebook", "Facebook"
    GOOGLE = "google", "Google / search"
    REFERRAL = "referral", "Member referral"
    # Posted straight in by the gym's own marketing site through the leads
    # API. Its own value rather than OTHER, because "is our website working"
    # is exactly the question this column exists to answer.
    WEBSITE = "website", "Gym website"
    OTHER = "other", "Other"


class Enquiry(models.Model):
    """Someone who asked about the gym and needs following up.

    `follow_up_on` is a date and not a datetime on purpose: the front desk
    decides *which day* to ring someone, never a to-the-minute slot, and storing
    a time would only invite a timezone bug into a field nobody sets.
    """
    # The branch this belongs to. Operational data is isolated per building:
    # "who came in yesterday" is a question about a gym, not about a brand.
    # Nullable for now; the backfill fills it and a later migration requires it.
    tenant = models.ForeignKey(
        "tenancy.Tenant",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    follow_up_on = models.DateField(help_text="The day to call them back.")
    status = models.CharField(
        max_length=10, choices=EnquiryStatus.choices, default=EnquiryStatus.OPEN
    )
    source = models.CharField(
        max_length=10, choices=EnquirySource.choices, default=EnquirySource.WALK_IN
    )
    # Which plan they asked about, so lost leads can be read by price point.
    interested_in = models.ForeignKey(
        "billing.Plan",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="enquiries",
    )
    # Who is chasing this one. Blank means "whoever is on the desk".
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="enquiries_assigned",
    )
    # Set when the lead becomes a member account, which is what makes the
    # conversion rate a fact rather than a status somebody remembered to change.
    converted_user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="from_enquiry",
    )
    notes = models.TextField(blank=True)
    # Stamped when someone marks the call done, so "called today" survives a
    # follow-up being pushed to a later date.
    last_contacted_on = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="enquiries_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    #: Scoped to the branch that owns it; `.unscoped` is the way past
    #: this, and is deliberately awkward to type.
    tenant_field = "tenant"
    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        # Soonest call first, and anything overdue floats to the top.
        ordering = ["follow_up_on", "-created_at"]
        indexes = [models.Index(fields=["status", "follow_up_on"])]
        verbose_name_plural = "enquiries"

    @property
    def is_converted(self):
        return self.converted_user_id is not None

    @property
    def is_due(self):
        """Still open and the callback date has arrived (or passed)."""
        return self.status == EnquiryStatus.OPEN and self.follow_up_on <= timezone.localdate()

    @property
    def days_overdue(self):
        if self.status != EnquiryStatus.OPEN:
            return 0
        return max((timezone.localdate() - self.follow_up_on).days, 0)

    def __str__(self):
        return f"{self.name} ({self.phone}) - call {self.follow_up_on}"


class EnquiryNote(models.Model):
    """One entry in the trail of what was said and when.

    `Enquiry.last_contacted_on` answers "have we called them?"; this answers
    "what happened when we did", which is what the next person picking up the
    lead actually needs.
    """
    # The branch this belongs to. Operational data is isolated per building:
    # "who came in yesterday" is a question about a gym, not about a brand.
    # Nullable for now; the backfill fills it and a later migration requires it.
    tenant = models.ForeignKey(
        "tenancy.Tenant",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    enquiry = models.ForeignKey(Enquiry, on_delete=models.CASCADE, related_name="trail")
    body = models.TextField()
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="enquiry_notes",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    #: Scoped to the branch that owns it; `.unscoped` is the way past
    #: this, and is deliberately awkward to type.
    tenant_field = "tenant"
    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.enquiry.name}: {self.body[:40]}"


class RetentionPolicy(models.Model):
    """When the gym considers a member to be drifting away.

    A row rather than a setting in code, because the number that means "at
    risk" is different for a gym selling monthly memberships and one selling
    twelve-week programmes, and the owner should be able to change it without a
    redeploy.

    Only the thresholds live here. Who is actually at risk is never stored: it
    is read off the check-in history every time the list is asked for, so a
    member who walks in this morning drops off it without anything having to
    clear a flag -- the same reasoning that keeps membership status derived
    from the payment ledger.
    """
    # Shared across the brand's branches: a chain maintains one price list, one
    # badge ladder, one identity -- not one copy per building. Nullable for now;
    # the backfill fills it and a later migration makes it required.
    organisation = models.ForeignKey(
        "tenancy.Organisation",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    quiet_days = models.PositiveSmallIntegerField(
        default=10,
        help_text="No check-in for this many days and a member is worth a call.",
    )
    # A second, softer threshold so the desk can see people cooling off before
    # they have properly gone quiet.
    cooling_days = models.PositiveSmallIntegerField(
        default=5, help_text="Fewer days than this and the member is fine."
    )
    # Someone who joined yesterday hasn't 'gone quiet'; they just haven't been
    # in yet. This stops the list filling up with brand new members.
    grace_days = models.PositiveSmallIntegerField(
        default=7, help_text="New members are left alone for this many days."
    )
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    #: Scoped to the brand that owns it; `.unscoped` is the way past
    #: this, and is deliberately awkward to type.
    tenant_field = "organisation"
    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        ordering = ["-is_active", "-updated_at"]
        verbose_name_plural = "retention policies"
        constraints = [
            models.UniqueConstraint(
                fields=["organisation", "is_active"],
                condition=models.Q(is_active=True),
                name="one_active_retention_policy_per_organisation",
            ),
            # A softer threshold that isn't softer is a contradiction, and it
            # would silently produce an empty "cooling off" band.
            models.CheckConstraint(
                condition=models.Q(cooling_days__lt=models.F("quiet_days")),
                name="cooling_before_quiet",
            ),
        ]

    @classmethod
    def current(cls):
        return cls.objects.filter(is_active=True).first()

    def __str__(self):
        return f"Quiet after {self.quiet_days} days"
