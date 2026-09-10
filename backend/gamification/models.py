from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from tenancy.managers import TenantManager, UnscopedManager
from django.utils import timezone


class Tier(models.IntegerChoices):
    """Five rungs, so a badge set has somewhere to go without inflating.

    The names are the rung, not the achievement -- "Bronze" says how hard a
    badge was to get, while the badge's own name says what it was for.
    """

    BRONZE = 1, "Bronze"
    SILVER = 2, "Silver"
    GOLD = 3, "Gold"
    PLATINUM = 4, "Platinum"
    ELITE = 5, "Elite"


class Criterion(models.TextChoices):
    """What a badge is measured against.

    A closed list rather than free text: every one of these is something the
    database can already answer from existing rows, so a badge can never be
    defined against a number nothing computes.
    """

    VISITS = "visits", "Total gym visits"
    STREAK = "streak", "Longest daily streak"
    WORKOUTS = "workouts", "Workout sessions logged"
    SETS = "sets", "Sets logged"
    RECORDS = "records", "Personal records set"
    MONTHS = "months", "Months as a member"
    CLASSES = "classes", "Classes attended"
    # Months in a row with at least one visit. A *daily* streak long enough to
    # mean "kept it up for half a year" is not a thing anybody does, so a
    # six-month milestone has to be measured in months that were trained in.
    MONTH_STREAK = "month_streak", "Consecutive months trained"
    # The only criterion measured against a weight rather than a count, and the
    # only one that needs an exercise to be meaningful: "100kg" is a milestone
    # on the squat and a different one entirely on the overhead press.
    LIFT = "lift", "Heaviest lift on one exercise (kg)"


class Badge(models.Model):
    """One earnable badge.

    `image` is deliberately optional. The tiers ship without artwork so the gym
    can upload its own later; until then the portal draws a tier-coloured
    placeholder rather than a broken image.
    """
    # Shared across the brand's branches: a chain maintains one price list, one
    # badge ladder, one identity -- not one copy per building. Nullable for now;
    # the backfill fills it and a later migration makes it required.
    organisation = models.ForeignKey(
        "tenancy.Organisation",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    code = models.SlugField(
        max_length=50, help_text="Stable id, e.g. 'first-50-visits'."
    )
    name = models.CharField(max_length=80)
    description = models.CharField(max_length=200, blank=True)
    tier = models.PositiveSmallIntegerField(choices=Tier.choices, default=Tier.BRONZE)
    image = models.ImageField(upload_to="badges/", null=True, blank=True)
    criterion = models.CharField(max_length=16, choices=Criterion.choices)
    # Only meaningful for the LIFT criterion, and required there -- the
    # constraint below is what stops a "100kg" badge existing with no
    # statement of 100kg of what.
    exercise = models.ForeignKey(
        "workouts.Exercise",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="badges",
    )
    threshold = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text="The number to reach: a count, or kilograms for a lift badge.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    #: Scoped to the brand that owns it; `.unscoped` is the way past
    #: this, and is deliberately awkward to type.
    tenant_field = "organisation"
    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        # Hardest last within a criterion, so a member reads their ladder in
        # the order they will climb it.
        ordering = ["criterion", "threshold"]
        constraints = [
            # Unchanged for every counting criterion. Left as its own
            # constraint rather than widened to include `exercise`, because
            # NULLs are distinct in a unique index -- adding the column would
            # have quietly allowed two identical "50 visits" badges.
            models.UniqueConstraint(
                fields=["organisation", "code"], name="one_badge_code_per_organisation"
            ),
            models.UniqueConstraint(
                fields=["organisation", "criterion", "threshold"],
                condition=~models.Q(criterion="lift"),
                name="one_badge_per_criterion_threshold",
            ),
            models.UniqueConstraint(
                fields=["organisation", "exercise", "threshold"],
                condition=models.Q(criterion="lift"),
                name="one_lift_badge_per_exercise_weight",
            ),
            # A lift badge names an exercise; nothing else does.
            models.CheckConstraint(
                condition=(
                    models.Q(criterion="lift", exercise__isnull=False)
                    | (~models.Q(criterion="lift") & models.Q(exercise__isnull=True))
                ),
                name="only_lift_badges_name_an_exercise",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_tier_display()})"


class MemberBadge(models.Model):
    """A badge someone has earned.

    This is the one thing here worth storing: *that* it was earned, and when.
    Whether the member still meets the criterion is not re-checked -- a badge
    you can lose by having a quiet month isn't a badge, it's a status bar.
    """
    # Logged in the context of one gym's programme, trainers and badges. A
    # member who trains at two gyms has a history at each; Gym A's sets must not
    # feed Gym B's leaderboards.
    tenant = models.ForeignKey(
        "tenancy.Tenant",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    member = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="badges"
    )
    badge = models.ForeignKey(Badge, on_delete=models.CASCADE, related_name="awards")
    awarded_on = models.DateField(default=timezone.localdate)
    # What the member's number actually was when it was awarded, kept so the
    # award can be explained later even if the badge's threshold is edited.
    value_at_award = models.PositiveIntegerField(default=0)

    #: Scoped to the branch that owns it; `.unscoped` is the way past
    #: this, and is deliberately awkward to type.
    tenant_field = "tenant"
    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        ordering = ["-awarded_on", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["member", "badge"], name="one_award_per_badge")
        ]

    def __str__(self):
        return f"{self.member} - {self.badge.name}"


class GamificationProfile(models.Model):
    """Per-member settings. Only one so far, and it matters: the leaderboard is
    opt-in, so nobody's lifts are published because a feature shipped."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="gamification"
    )
    leaderboard_opt_in = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user} (leaderboard: {'in' if self.leaderboard_opt_in else 'out'})"


class PersonalRecord(models.Model):
    """The heaviest set a member has done on one exercise, on one day.

    `bodyweight_kg` is a snapshot taken at the moment of the lift, not a lookup
    against whatever the member weighs now. Dividing an old PR by today's
    bodyweight would rewrite history every time somebody stepped on the scales
    -- a member who lost 5kg would see last year's squat get better on its own.

    The ratio itself is not stored: it is `weight / bodyweight_kg`, computed on
    read from two columns that are already here.
    """
    # Logged in the context of one gym's programme, trainers and badges. A
    # member who trains at two gyms has a history at each; Gym A's sets must not
    # feed Gym B's leaderboards.
    tenant = models.ForeignKey(
        "tenancy.Tenant",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    member = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="records"
    )
    exercise = models.ForeignKey(
        "workouts.Exercise", on_delete=models.CASCADE, related_name="records"
    )
    weight_kg = models.DecimalField(max_digits=6, decimal_places=2)
    reps = models.PositiveIntegerField()
    # Null when the member had never been weighed before this lift. The PR is
    # still theirs; it just can't be scored on a leaderboard that divides by
    # bodyweight, and it is left out rather than guessed at.
    bodyweight_kg = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    achieved_on = models.DateField()
    # The set this came from, so a deleted log takes its record with it.
    log = models.OneToOneField(
        "workouts.WorkoutLog",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="record",
    )
    # When the member was actually shown the "new PR" moment. One of the very
    # few things in this app that genuinely cannot be derived: whether a person
    # has seen something is not recoverable from any other row. Records older
    # than the celebration window are stamped on creation, so importing years
    # of history does not greet the member with a hundred party poppers.
    seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    #: Scoped to the branch that owns it; `.unscoped` is the way past
    #: this, and is deliberately awkward to type.
    tenant_field = "tenant"
    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        ordering = ["-achieved_on", "-weight_kg"]
        indexes = [models.Index(fields=["exercise", "-achieved_on"])]
        constraints = [
            # One record per member per exercise per day: a member who beats
            # their own PR twice in a session has one record for that day, the
            # heaviest.
            models.UniqueConstraint(
                fields=["member", "exercise", "achieved_on"],
                name="one_record_per_exercise_per_day",
            )
        ]

    @property
    def ratio(self):
        """Weight lifted per kilo of the lifter, at the time they lifted it."""
        if not self.bodyweight_kg:
            return None
        return (Decimal(self.weight_kg) / Decimal(self.bodyweight_kg)).quantize(
            Decimal("0.01")
        )

    def __str__(self):
        return f"{self.member} - {self.exercise} {self.weight_kg}kg"
