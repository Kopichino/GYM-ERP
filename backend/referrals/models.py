import secrets
import string

from django.conf import settings
from django.db import models

from tenancy.managers import TenantManager, UnscopedManager
from django.utils import timezone

from billing.models import PaymentStatus

# No 0/O or 1/I: these codes get read out over a phone.
ALPHABET = "".join(c for c in string.ascii_uppercase + string.digits if c not in "O0I1")


def make_code(length=6):
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


class ReferralStatus(models.TextChoices):
    PENDING = "pending", "Not signed up yet"
    SIGNED_UP = "signed_up", "Signed up, not paid"
    JOINED = "joined", "Joined and paid"


class ReferralProgram(models.Model):
    """What the gym is currently offering for a referral.

    A single active row rather than a setting in code, because the offer is the
    kind of thing a gym changes for a month and then changes back, and the
    member-facing page has to say what today's offer actually is.
    """
    # Shared across the brand's branches: a chain maintains one price list, one
    # badge ladder, one identity -- not one copy per building. Nullable for now;
    # the backfill fills it and a later migration makes it required.
    organisation = models.ForeignKey(
        "tenancy.Organisation",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    reward_days = models.PositiveSmallIntegerField(
        default=15, help_text="Free days added to the referrer's membership."
    )
    blurb = models.CharField(
        max_length=200,
        blank=True,
        help_text="What members are told, e.g. 'Bring a friend, train 15 days on us.'",
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
        constraints = [
            models.UniqueConstraint(
                fields=["organisation", "is_active"],
                condition=models.Q(is_active=True),
                name="one_active_referral_program_per_organisation",
            )
        ]

    @classmethod
    def current(cls):
        return cls.objects.filter(is_active=True).first()

    def __str__(self):
        return f"{self.reward_days} free days" + ("" if self.is_active else " (inactive)")


class Referral(models.Model):
    """One member vouching for one person.

    How far along it is isn't a column: it's read off whether the referred
    person has an account and whether that account has a completed payment.
    A stored status would go stale the moment a payment was refunded, which is
    the same reason membership status is derived from the ledger.
    """
    # Logged in the context of one gym's programme, trainers and badges. A
    # member who trains at two gyms has a history at each; Gym A's sets must not
    # feed Gym B's leaderboards.
    tenant = models.ForeignKey(
        "tenancy.Tenant",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    referrer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="referrals_made"
    )
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    # Set once the person actually creates an account, by signing up with the
    # referrer's code or by the front desk linking them.
    referred_user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="referred_by_record",
    )
    # Referrals feed the same follow-up list as walk-in enquiries, so the front
    # desk works one queue rather than two.
    enquiry = models.OneToOneField(
        "crm.Enquiry", null=True, blank=True, on_delete=models.SET_NULL, related_name="referral"
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    #: Scoped to the branch that owns it; `.unscoped` is the way past
    #: this, and is deliberately awkward to type.
    tenant_field = "tenant"
    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["referrer", "-created_at"])]

    @property
    def status(self):
        if self.referred_user_id is None:
            return ReferralStatus.PENDING
        has_paid = self.referred_user.payments.filter(status=PaymentStatus.COMPLETED).exists()
        return ReferralStatus.JOINED if has_paid else ReferralStatus.SIGNED_UP

    @property
    def is_rewardable(self):
        """Earned the reward and hasn't been paid it yet."""
        return self.status == ReferralStatus.JOINED and not hasattr(self, "reward")

    def __str__(self):
        return f"{self.referrer} -> {self.name}"


class ReferralReward(models.Model):
    """The free days actually given, and the payment row that granted them.

    The days are applied by writing a zero-amount payment through the usual
    billing service, so the referrer's expiry and derived status move exactly
    as they would for a paid renewal -- there is no second way for a membership
    to gain time.
    """

    referral = models.OneToOneField(Referral, on_delete=models.CASCADE, related_name="reward")
    days_granted = models.PositiveSmallIntegerField()
    payment = models.ForeignKey(
        "billing.Payment",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="referral_rewards",
    )
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="referral_rewards_granted",
    )
    granted_on = models.DateField(default=timezone.localdate)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-granted_on", "-id"]

    def __str__(self):
        return f"{self.days_granted} days to {self.referral.referrer}"
