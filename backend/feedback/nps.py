"""Turning answers into a score, and working out who is owed a prompt.

Nothing in here is stored. The Net Promoter Score is recomputed from the
responses on every read, and "does this member have a survey waiting?" is
answered by looking for an occasion -- a finished visit, a completed PT session
-- that has no response against it yet. There is no pending-prompt table to get
out of step with reality.
"""

from datetime import timedelta

from django.db.models import Avg, Count, Q
from django.utils import timezone

from attendance.models import CheckInOut
from pt.models import PTSession, SessionStatus

from .models import DETRACTOR_TO, PROMOTER_FROM, Survey, SurveyResponse, Trigger

DEFINITION = (
    "Promoters (9-10) minus detractors (0-6), as a percentage of everyone who "
    "answered. Runs from -100 to +100."
)


def score(responses):
    """The NPS of a set of responses, plus the counts it came from.

    The counts travel with the score on purpose: +100 from two answers and +100
    from two hundred are the same number and completely different facts.
    """
    stats = responses.aggregate(
        total=Count("id"),
        promoters=Count("id", filter=Q(score__gte=PROMOTER_FROM)),
        detractors=Count("id", filter=Q(score__lte=DETRACTOR_TO)),
        average=Avg("score"),
    )
    total = stats["total"]
    promoters = stats["promoters"]
    detractors = stats["detractors"]
    return {
        "responses": total,
        "promoters": promoters,
        "passives": total - promoters - detractors,
        "detractors": detractors,
        "nps": round((promoters - detractors) * 100 / total, 1) if total else None,
        "average": round(stats["average"], 2) if stats["average"] is not None else None,
    }


def _window(start=None, end=None, survey=None):
    responses = SurveyResponse.objects.all()
    if survey is not None:
        responses = responses.filter(survey=survey)
    if start:
        responses = responses.filter(created_at__date__gte=start)
    if end:
        responses = responses.filter(created_at__date__lte=end)
    return responses


def summary(start=None, end=None, survey=None):
    """Headline score for a window, with the comments worth reading.

    Detractor comments are surfaced separately because they are the only part
    of a survey that tells you what to change; a score on its own says
    something is wrong without saying what.
    """
    responses = _window(start, end, survey)
    result = score(responses)
    result["definition"] = DEFINITION
    result["detractor_comments"] = [
        {
            "id": row.id,
            "score": row.score,
            "comment": row.comment,
            "member": row.member.get_full_name() or row.member.username,
            "member_id": row.member_id,
            "created_at": row.created_at,
        }
        for row in responses.filter(score__lte=DETRACTOR_TO)
        .exclude(comment="")
        .select_related("member")[:20]
    ]
    return result


def trend(months=6, survey=None):
    """Month by month, so a falling score is visible before it is a crisis."""
    today = timezone.localdate()
    out = []
    cursor = today.replace(day=1)
    for _ in range(months):
        # Last day of this month, by stepping back from the first of the next.
        nxt = (cursor + timedelta(days=32)).replace(day=1)
        month = score(_window(cursor, nxt - timedelta(days=1), survey))
        month["month"] = cursor.isoformat()
        out.append(month)
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    return list(reversed(out))


def _answered_recently(survey, member):
    """True if the member is inside this survey's cooldown."""
    if not survey.cooldown_days:
        return False
    since = timezone.now() - timedelta(days=survey.cooldown_days)
    return SurveyResponse.objects.filter(
        survey=survey, member=member, created_at__gte=since
    ).exists()


def pending(member):
    """The prompts this member is owed right now, newest occasion first.

    A live survey plus an occasion that has not been answered against. Asked on
    every dashboard load, which is why it stays a couple of indexed lookups and
    not a scan.
    """
    out = []
    for survey in Survey.objects.filter(is_active=True):
        if _answered_recently(survey, member):
            continue

        occasion = None
        if survey.trigger == Trigger.POST_CHECKIN:
            # A finished visit only. Asking someone how their session was while
            # they are still mid-set is worse than not asking.
            occasion = (
                CheckInOut.objects.filter(user=member, check_out_time__isnull=False)
                .exclude(survey_responses__survey=survey)
                .order_by("-check_in_time")
                .first()
            )
            if occasion is None:
                continue
        elif survey.trigger == Trigger.POST_PT:
            occasion = (
                PTSession.objects.filter(member=member, status=SessionStatus.COMPLETED)
                .exclude(survey_responses__survey=survey)
                .order_by("-date", "-start_time")
                .first()
            )
            if occasion is None:
                continue

        out.append(
            {
                "survey": survey,
                "visit": occasion if survey.trigger == Trigger.POST_CHECKIN else None,
                "pt_session": occasion if survey.trigger == Trigger.POST_PT else None,
            }
        )
    return out
