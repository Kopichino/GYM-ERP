from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


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
