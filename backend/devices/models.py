import hashlib
import secrets

from django.db import models

from tenancy.managers import TenantManager, UnscopedManager


def generate_key():
    """Returns (plaintext, hash). The plaintext is shown to the admin once at
    registration and never stored -- only its hash is kept, the same way a
    password would be."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_key(raw)


def hash_key(raw):
    return hashlib.sha256(raw.encode()).hexdigest()


class DeviceKind(models.TextChoices):
    """What the hardware actually does, which decides whether it may refuse
    someone. A terminal only writes attendance down; a turnstile or a lock
    stands between the member and the gym floor."""

    TERMINAL = "terminal", "Attendance terminal"
    TURNSTILE = "turnstile", "Turnstile"
    DOOR = "door", "Door lock"


class Device(models.Model):
    """A fingerprint or face terminal at the door. A device is not a person and
    cannot hold a JWT, so it authenticates with its own API key."""
    # The branch this belongs to. Operational data is isolated per building:
    # "who came in yesterday" is a question about a gym, not about a brand.
    # Nullable for now; the backfill fills it and a later migration requires it.
    tenant = models.ForeignKey(
        "tenancy.Tenant",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    name = models.CharField(max_length=100)
    serial = models.CharField(max_length=100, unique=True)
    location = models.CharField(max_length=120, blank=True)
    # Defaults to a plain terminal so every device registered before access
    # control existed keeps behaving exactly as it did: recording attendance
    # and never turning anyone away.
    kind = models.CharField(
        max_length=10, choices=DeviceKind.choices, default=DeviceKind.TERMINAL
    )
    # Days past expiry a lapsed member is still let through. Zero locks them
    # out the morning after; a day or two lets the front desk have the
    # conversation instead of the hardware having it for them.
    grace_days = models.PositiveSmallIntegerField(
        default=0, help_text="Days after expiry a lapsed member may still enter."
    )
    api_key_hash = models.CharField(max_length=64, unique=True)
    is_active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    #: Scoped to the branch that owns it; `.unscoped` is the way past
    #: this, and is deliberately awkward to type.
    tenant_field = "tenant"
    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.serial})"


class EventOutcome(models.TextChoices):
    PENDING = "pending", "Pending"
    CHECKED_IN = "checked_in", "Checked in"
    CHECKED_OUT = "checked_out", "Checked out"
    UNMATCHED = "unmatched", "No matching member"
    DUPLICATE = "duplicate", "Duplicate punch"
    # Someone real, refused entry. Worth its own outcome rather than a failure:
    # a denial is the system working, and it is the queue the front desk most
    # needs to see.
    DENIED = "denied", "Refused entry"
    FAILED = "failed", "Failed"


class DeviceEvent(models.Model):
    """One raw punch, stored before it is interpreted.

    Terminals push duplicates and clock-skewed timestamps, so the log is
    append-only: if the mapping from biometric id to member is wrong, the punch
    can be reprocessed instead of a day's attendance being lost.
    """
    # The branch this belongs to. Operational data is isolated per building:
    # "who came in yesterday" is a question about a gym, not about a brand.
    # Nullable for now; the backfill fills it and a later migration requires it.
    tenant = models.ForeignKey(
        "tenancy.Tenant",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="events")
    biometric_id = models.CharField(max_length=64)
    event_time = models.DateTimeField()
    raw_payload = models.JSONField(default=dict, blank=True)
    outcome = models.CharField(
        max_length=12, choices=EventOutcome.choices, default=EventOutcome.PENDING
    )
    detail = models.CharField(max_length=200, blank=True)
    member = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="device_events"
    )
    check_in = models.ForeignKey(
        "attendance.CheckInOut",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="device_events",
    )
    received_at = models.DateTimeField(auto_now_add=True)

    #: Scoped to the branch that owns it; `.unscoped` is the way past
    #: this, and is deliberately awkward to type.
    tenant_field = "tenant"
    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        ordering = ["-event_time", "-id"]
        constraints = [
            # Terminals re-send their buffer after a network drop; the same
            # punch must not open a second visit.
            models.UniqueConstraint(
                fields=["device", "biometric_id", "event_time"], name="one_punch_per_device_time"
            )
        ]

    def __str__(self):
        return f"{self.biometric_id} @ {self.event_time} ({self.outcome})"
