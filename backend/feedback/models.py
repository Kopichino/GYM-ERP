"""Asking members how it is going, and reading the answer honestly.

Two tables only: the question, and the answers. The Net Promoter Score itself
is never stored -- it is worked out from the responses every time it is asked
for, so it cannot drift away from the rows it came from and there is no
recalculation job to forget. Same reasoning as the derived membership status
and the derived at-risk list.
"""

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from tenancy.managers import TenantManager, UnscopedManager

# The standard NPS bands. Named here rather than repeated as magic numbers in
# the aggregation, because "9 and 10 are promoters" is the definition, not an
# implementation detail.
PROMOTER_FROM = 9
DETRACTOR_TO = 6


class Trigger(models.TextChoices):
    POST_CHECKIN = "post_checkin", "After a visit"
    POST_PT = "post_pt", "After a personal training session"
    MANUAL = "manual", "Any time"


class Survey(models.Model):
    """One question, and the moment it gets asked.

    A row rather than a hard-coded prompt: the wording an owner wants and the
    moment they want it asked are both things that change without a redeploy.
    """
    # Shared across the brand's branches: a chain maintains one price list, one
    # badge ladder, one identity -- not one copy per building. Nullable for now;
    # the backfill fills it and a later migration makes it required.
    organisation = models.ForeignKey(
        "tenancy.Organisation",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    title = models.CharField(max_length=120)
    question = models.CharField(
        max_length=200,
        default="How likely are you to recommend us to a friend?",
        help_text="Shown above the 0-10 scale.",
    )
    trigger = models.CharField(
        max_length=12, choices=Trigger.choices, default=Trigger.MANUAL
    )
    # Without this a post-visit survey asks the same member after every single
    # visit, which is how a feedback prompt becomes something people learn to
    # dismiss without reading.
    cooldown_days = models.PositiveSmallIntegerField(
        default=90, help_text="Leave a member alone for this long after they answer."
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    #: Scoped to the brand that owns it; `.unscoped` is the way past
    #: this, and is deliberately awkward to type.
    tenant_field = "organisation"
    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        ordering = ["-is_active", "-created_at"]
        constraints = [
            # Two live surveys on the same trigger would both fire at the same
            # moment and the member would be asked twice for one visit. Same
            # shape as the one-active-policy rules elsewhere.
            models.UniqueConstraint(
                fields=["organisation", "trigger"],
                condition=models.Q(is_active=True),
                name="one_active_survey_per_trigger_per_organisation",
            ),
        ]

    def __str__(self):
        return self.title


class SurveyResponse(models.Model):
    """One member's answer, tied to the occasion that prompted it.

    Keeping the occasion is what makes "is this member owed a prompt?"
    answerable without storing a pending-prompt table: a visit with no response
    against it is an unanswered prompt, and a visit with one is done.
    """
    # The branch this belongs to. Operational data is isolated per building:
    # "who came in yesterday" is a question about a gym, not about a brand.
    # Nullable for now; the backfill fills it and a later migration requires it.
    tenant = models.ForeignKey(
        "tenancy.Tenant",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    survey = models.ForeignKey(
        Survey, on_delete=models.CASCADE, related_name="responses"
    )
    member = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="survey_responses"
    )
    score = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(10)],
        help_text="0 to 10.",
    )
    comment = models.TextField(blank=True)
    # The occasion. Null for a manual survey, which has no occasion beyond the
    # member choosing to answer.
    visit = models.ForeignKey(
        "attendance.CheckInOut",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="survey_responses",
    )
    pt_session = models.ForeignKey(
        "pt.PTSession",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="survey_responses",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    #: Scoped to the branch that owns it; `.unscoped` is the way past
    #: this, and is deliberately awkward to type.
    tenant_field = "tenant"
    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["survey", "created_at"])]
        constraints = [
            # The validators above only run through a serializer or a full
            # clean; this is what actually stops an 11 reaching the table and
            # quietly inflating every promoter count computed from it.
            models.CheckConstraint(
                condition=models.Q(score__gte=0, score__lte=10),
                name="survey_score_is_zero_to_ten",
            ),
            # One answer per occasion. A double-tapped Send is the ordinary way
            # this happens, and two rows would count one opinion twice.
            models.UniqueConstraint(
                fields=["survey", "visit"],
                condition=models.Q(visit__isnull=False),
                name="one_response_per_visit",
            ),
            models.UniqueConstraint(
                fields=["survey", "pt_session"],
                condition=models.Q(pt_session__isnull=False),
                name="one_response_per_pt_session",
            ),
        ]

    @property
    def band(self):
        if self.score >= PROMOTER_FROM:
            return "promoter"
        if self.score <= DETRACTOR_TO:
            return "detractor"
        return "passive"

    def __str__(self):
        return f"{self.member} scored {self.score}"
