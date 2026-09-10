from rest_framework import serializers

from .models import Survey, SurveyResponse, Trigger


class SurveySerializer(serializers.ModelSerializer):
    trigger_name = serializers.CharField(source="get_trigger_display", read_only=True)
    response_count = serializers.IntegerField(source="responses.count", read_only=True)
    # Same reason as the PT availability window: a form-encoded POST omits an
    # unchecked box entirely, and DRF reads a missing boolean as False -- which
    # would create every survey switched off and asking nobody anything.
    is_active = serializers.BooleanField(required=False, default=True)
    # Declared by hand to drop the unique validator DRF builds from the
    # single-field one-active-survey-per-trigger index. Clearing Meta.validators
    # does not reach a field-level one, and it answered a clash with "survey
    # with this trigger already exists" -- true, and useless to the owner, who
    # needs to be told which survey and what to do about it.
    trigger = serializers.ChoiceField(
        choices=Trigger.choices, required=False, default=Trigger.MANUAL
    )

    class Meta:
        model = Survey
        fields = [
            "id",
            "title",
            "question",
            "trigger",
            "trigger_name",
            "cooldown_days",
            "is_active",
            "response_count",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]
        # The model's one-active-survey-per-trigger index becomes a DRF
        # validator that reports "The fields trigger must make a unique set",
        # which tells an owner nothing about what to do. The view answers in
        # words instead; the index still stands in the database.
        validators = []


class SurveyResponseSerializer(serializers.ModelSerializer):
    member_name = serializers.SerializerMethodField()
    survey_title = serializers.CharField(source="survey.title", read_only=True)
    band = serializers.CharField(read_only=True)

    class Meta:
        model = SurveyResponse
        fields = [
            "id",
            "survey",
            "survey_title",
            "member",
            "member_name",
            "score",
            "band",
            "comment",
            "visit",
            "pt_session",
            "created_at",
        ]
        read_only_fields = ["id", "member", "created_at"]
        validators = []

    def get_member_name(self, obj):
        return obj.member.get_full_name() or obj.member.username


class PendingPromptSerializer(serializers.Serializer):
    """A prompt that is owed -- derived, with no row of its own."""

    survey = SurveySerializer()
    visit = serializers.PrimaryKeyRelatedField(read_only=True)
    pt_session = serializers.PrimaryKeyRelatedField(read_only=True)
