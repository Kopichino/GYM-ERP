from rest_framework import serializers

from core.uniqueness import Rule, SaveConflictsAsValidationErrors, UniqueInScope

from .models import Badge, Criterion, GamificationProfile, MemberBadge, PersonalRecord


class BadgeSerializer(SaveConflictsAsValidationErrors, serializers.ModelSerializer):
    tier_name = serializers.CharField(source="get_tier_display", read_only=True)
    criterion_name = serializers.CharField(source="get_criterion_display", read_only=True)
    # How many members hold it, so an admin can see whether a threshold is set
    # somewhere reachable.
    awarded_count = serializers.IntegerField(source="awards.count", read_only=True)
    exercise_name = serializers.CharField(source="exercise.name", read_only=True, default=None)

    class Meta:
        model = Badge
        fields = [
            "id",
            "code",
            "name",
            "description",
            "tier",
            "tier_name",
            # Left empty until the gym uploads its own artwork; the portal
            # draws a tier-coloured placeholder in the meantime.
            "image",
            "criterion",
            "criterion_name",
            # Only set on a lift badge -- "100kg" means nothing without it.
            "exercise",
            "exercise_name",
            "threshold",
            "is_active",
            "awarded_count",
        ]
        read_only_fields = ["id", "awarded_count"]
        # The three unique constraints on Badge, said in words. A lift badge is
        # unique by exercise and weight; any other by criterion and threshold.
        validators = [
            UniqueInScope(
                Rule("code", "A badge with this code already exists."),
                Rule(
                    ("criterion", "threshold"),
                    "There is already a badge for this at that threshold.",
                    applies=lambda values: values["criterion"] != Criterion.LIFT,
                ),
                Rule(
                    ("criterion", "exercise", "threshold"),
                    "There is already a lift badge for this exercise at that weight.",
                    applies=lambda values: values["criterion"] == Criterion.LIFT,
                ),
            )
        ]

    def validate_image(self, image):
        from core.uploads import validate_image_upload

        return validate_image_upload(image)

    def validate(self, attrs):
        """Say in words what the check constraint would otherwise say as a 500.

        The database is still the thing that guarantees this; the point here is
        only that an admin gets told which field to fix.
        """
        criterion = attrs.get(
            "criterion", getattr(self.instance, "criterion", None)
        )
        exercise = attrs.get("exercise", getattr(self.instance, "exercise", None))

        if criterion == Criterion.LIFT and exercise is None:
            raise serializers.ValidationError(
                {"exercise": "A lift badge has to say which exercise the weight is on."}
            )
        if criterion != Criterion.LIFT and exercise is not None:
            raise serializers.ValidationError(
                {"exercise": "Only a lift badge names an exercise."}
            )
        return attrs


class BadgeProgressSerializer(serializers.Serializer):
    """A badge plus where this member stands against it -- derived, not stored."""

    badge = BadgeSerializer()
    earned = serializers.BooleanField()
    awarded_on = serializers.DateField(allow_null=True)
    value = serializers.IntegerField()
    threshold = serializers.IntegerField()
    percent = serializers.IntegerField()


class MemberBadgeSerializer(serializers.ModelSerializer):
    badge = BadgeSerializer(read_only=True)

    class Meta:
        model = MemberBadge
        fields = ["id", "badge", "awarded_on", "value_at_award"]
        read_only_fields = fields


class GamificationProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = GamificationProfile
        fields = ["leaderboard_opt_in", "updated_at"]
        read_only_fields = ["updated_at"]


class PersonalRecordSerializer(serializers.ModelSerializer):
    exercise_name = serializers.CharField(source="exercise.name", read_only=True)
    muscle_group = serializers.CharField(source="exercise.muscle_group", read_only=True)
    # weight / bodyweight at the time, computed on read from two stored columns.
    ratio = serializers.DecimalField(max_digits=6, decimal_places=2, read_only=True)

    class Meta:
        model = PersonalRecord
        fields = [
            "id",
            "exercise",
            "exercise_name",
            "muscle_group",
            "weight_kg",
            "reps",
            "bodyweight_kg",
            "ratio",
            "achieved_on",
        ]
        read_only_fields = fields


class LeaderboardRowSerializer(serializers.Serializer):
    rank = serializers.IntegerField()
    member_id = serializers.IntegerField()
    username = serializers.CharField()
    full_name = serializers.CharField()
    exercise_id = serializers.IntegerField()
    exercise = serializers.CharField()
    weight_kg = serializers.DecimalField(max_digits=6, decimal_places=2)
    reps = serializers.IntegerField()
    bodyweight_kg = serializers.DecimalField(max_digits=5, decimal_places=2)
    ratio = serializers.DecimalField(max_digits=6, decimal_places=2)
    achieved_on = serializers.DateField()


class PRCelebrationSerializer(serializers.Serializer):
    """A personal record with what it beat. The comparison is derived on read."""

    id = serializers.IntegerField()
    exercise = serializers.CharField()
    exercise_id = serializers.IntegerField()
    weight_kg = serializers.DecimalField(max_digits=6, decimal_places=2)
    reps = serializers.IntegerField()
    achieved_on = serializers.DateField()
    previous_kg = serializers.DecimalField(
        max_digits=6, decimal_places=2, allow_null=True
    )
    gain_kg = serializers.DecimalField(max_digits=6, decimal_places=2, allow_null=True)
    is_first = serializers.BooleanField()
    ratio = serializers.DecimalField(max_digits=6, decimal_places=2, allow_null=True)


class StandingSerializer(serializers.Serializer):
    """A member's own position, told only to them. Names nobody else."""

    month_start = serializers.DateField()
    exercise_id = serializers.IntegerField()
    ratio = serializers.DecimalField(max_digits=6, decimal_places=2, allow_null=True)
    pool = serializers.IntegerField()
    rank = serializers.IntegerField(allow_null=True)
    #: "Top 10%" -- rank as a share of the pool, rounded up.
    top_percent = serializers.IntegerField(allow_null=True)
    #: "Better than 90%" -- the share strictly below them.
    better_than = serializers.IntegerField(allow_null=True)
    reason = serializers.CharField(allow_null=True)
