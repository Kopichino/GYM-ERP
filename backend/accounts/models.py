from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from .session_policy import KINDS, NORMAL, REMEMBER, TRUSTED


class Role(models.TextChoices):
    MEMBER = "member", "Member"
    TRAINER = "trainer", "Trainer"
    ADMIN = "admin", "Admin"


class User(AbstractUser):
    """One person, across every gym on the platform.

    There is deliberately no `is_admin` / `is_trainer` / `is_member` here any
    more. On a platform running many gyms those questions have no answer
    without naming one: the same person can own a gym, coach at a second, and
    train at a third. Role lives on `tenancy.Membership`, and the answer comes
    from `request.access`, which the tenant middleware resolves per request.

    They were deleted rather than deprecated on purpose. A shim would have let
    old call sites keep returning a plausible answer to the wrong question;
    removing them turns every one into an AttributeError the tests catch.
    """

    email = models.EmailField(unique=True)
    # The role this account was created with, used only as the default when
    # opening its first Membership. It is NOT authoritative and nothing should
    # branch on it -- Membership is the source of truth. Kept for now because
    # signup and the importer both set it; a later migration retires it.
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["email"]

    def save(self, *args, **kwargs):
        # `is_staff` means *platform* staff -- access to Django's own /admin/,
        # which is not tenant-scoped and shows every gym's data at once. It was
        # previously mirrored from role==ADMIN, which on a multi-tenant install
        # would have handed every gym owner a console over all the others.
        # Nothing derives it now; only a superuser gets it automatically.
        if self.is_superuser:
            self.is_staff = True
        super().save(*args, **kwargs)

    def __str__(self):
        return self.get_full_name() or self.username


class MembershipStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    PAUSED = "paused", "Paused"
    EXPIRED = "expired", "Expired"


class MemberProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    trainer = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_members",
        limit_choices_to={"role": Role.TRAINER},
    )
    phone = models.CharField(max_length=20, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    # Height belongs to the profile because it barely changes; weight is a time
    # series and lives in bodystats.BodyMeasurement instead. BMI is derived from
    # the two and never stored.
    height_cm = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(50), MaxValueValidator(300)],
        help_text="Standing height in centimetres, used for BMI.",
    )
    join_date = models.DateField(auto_now_add=True)
    membership_status = models.CharField(
        max_length=10, choices=MembershipStatus.choices, default=MembershipStatus.ACTIVE
    )
    # Enrolment id from the fingerprint/face terminal, if the gym uses one.
    # Unique so a punch resolves to exactly one member; null for everyone else,
    # and Postgres/SQLite both allow many nulls under a unique index.
    biometric_id = models.CharField(max_length=64, null=True, blank=True, unique=True)
    # The member's own share-with-a-friend code. Stored rather than derived
    # because it has to be looked up by the code someone types at signup, and a
    # derived code would mean scanning every member to resolve one.
    referral_code = models.CharField(max_length=12, null=True, blank=True, unique=True)
    emergency_contact_name = models.CharField(max_length=150, blank=True)
    emergency_contact_phone = models.CharField(max_length=20, blank=True)
    photo = models.ImageField(upload_to="profile_photos/", null=True, blank=True)

    def __str__(self):
        return f"Profile: {self.user}"


class MfaDevice(models.Model):
    """The authenticator app this person signs in with.

    One per account rather than one per gym: like the password, two-step
    sign-in guards the person, who may belong to several gyms. `secret` is only
    live once `confirmed_at` is set. A new or replacement key waits in
    `pending_secret` until the person proves their app produces the right code,
    so a mistyped setup can never lock them out of a key that already works.

    Unlike a password, the key cannot be hashed -- the server has to compute
    the same codes the phone does -- so it is stored as the app needs it, and
    this table must be kept out of exports and logs.
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="mfa_device")
    secret = models.CharField(max_length=64, blank=True)
    pending_secret = models.CharField(max_length=64, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    #: The last time step a code was accepted for, so a code cannot be replayed
    #: inside its own half-minute.
    last_used_step = models.BigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Two-step sign-in: {self.user}"

    @property
    def is_confirmed(self):
        return self.confirmed_at is not None and bool(self.secret)


class MfaRecoveryCode(models.Model):
    """A single-use way in for someone who has lost their phone.

    Stored hashed. Issued ten at a time and shown exactly once; issuing a new
    set deletes the old one, so a sheet of codes left in a drawer stops working.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="mfa_recovery_codes")
    code_hash = models.CharField(max_length=64)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "code_hash"], name="recovery_code_unique_per_user"
            ),
        ]


class AuthSession(models.Model):
    """One signed-in browser or device: the thing a refresh token belongs to.

    A refresh token is replaced every time it is used, and SimpleJWT's own tables
    keep each one as an unrelated row -- so on their own they cannot say "this
    laptop", cannot be listed, and cannot be revoked one device at a time. This is
    the row that stays put while the tokens come and go.

    It carries the three things a long-lived sign-in needs:

    * a **ceiling** (`expires_at`), fixed at login from the kind of session and
      never moved by use -- the server enforces it as well as the token's own
      expiry, so neither alone is the only thing standing in the way;
    * a way to **end it** (`revoked_at`) that does not depend on the cache, so
      revoking survives a Redis outage exactly as blacklisting a token does;
    * enough to **recognise** it without keeping a secret: only a SHA-256 of the
      random session secret is stored. The secret itself lives in the signed
      refresh token in the httpOnly cookie and nowhere else.

    About the person, not a gym -- like the password and two-step sign-in, a
    session covers every gym the account belongs to, so nothing is tenant-scoped.
    No address is kept, and the label is a browser-and-system name, not the raw
    user agent.
    """

    KIND_CHOICES = [
        (NORMAL, "Normal"),
        (REMEMBER, "Remember me"),
        (TRUSTED, "Trusted device"),
    ]
    assert {key for key, _ in KIND_CHOICES} == set(KINDS)

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="auth_sessions")
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=NORMAL)
    secret_hash = models.CharField(max_length=64, unique=True)
    label = models.CharField(max_length=120, blank=True)
    #: The refresh token currently good for this session, so a rotation can be
    #: traced and the row and the token table cannot drift apart unnoticed.
    current_jti = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-last_seen_at"]
        indexes = [models.Index(fields=["user", "revoked_at"])]

    def __str__(self):
        return f"{self.get_kind_display()} session for {self.user} ({self.label or 'unknown device'})"

    @property
    def is_live(self):
        """Neither revoked nor past its ceiling, right now."""
        return self.revoked_at is None and self.expires_at > timezone.now()
