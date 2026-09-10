"""Who has stopped turning up.

Nothing here is stored. The list is rebuilt from the check-in history and the
payment ledger every time it is asked for, so a member who walks in this
morning is off it by lunchtime without any flag being cleared -- and a member
whose payment lapsed is described accurately rather than from a stale copy.

The two thresholds come from `RetentionPolicy`; the judgement of what to do
about someone stays with the person reading the list.
"""

from datetime import timedelta

from django.db.models import Max
from django.utils import timezone

from accounts.models import MembershipStatus, Role, User
from attendance.models import CheckInOut
from billing.services import get_latest_completed_payment

from .models import RetentionPolicy

# Used when nobody has set a policy yet, so the feature is useful the first
# time it is opened rather than empty until someone configures it.
DEFAULTS = {"quiet_days": 10, "cooling_days": 5, "grace_days": 7}


class Band:
    """How far gone someone is. Ordered worst-first, which is the order the
    front desk wants to work the list in."""

    QUIET = "quiet"
    COOLING = "cooling"


def thresholds():
    policy = RetentionPolicy.current()
    if policy is None:
        return DEFAULTS
    return {
        "quiet_days": policy.quiet_days,
        "cooling_days": policy.cooling_days,
        "grace_days": policy.grace_days,
    }


def _last_visit_map(members):
    """One query for everyone's most recent check-in, rather than one per
    member -- this list is read on a dashboard, not in a background job."""
    rows = (
        CheckInOut.objects.filter(user__in=members)
        .values("user_id")
        .annotate(last=Max("check_in_time"))
    )
    return {row["user_id"]: row["last"] for row in rows}


def at_risk(for_access=None, on=None):
    """Members who have gone quiet, worst first.

    `for_access` scopes the list the way the rest of the app scopes member data:
    an admin sees everyone, a trainer sees their own roster. Passing nobody
    means everyone, which is what the nightly digest wants.

    Members an admin has paused are left out -- a paused membership is someone
    who told us they'd be away, and chasing them is worse than saying nothing.
    """
    on = on or timezone.localdate()
    limits = thresholds()

    members = User.objects.filter(role=Role.MEMBER).select_related("profile")
    # A trainer sees only their own roster; an admin here sees the whole gym.
    if for_access is not None and not for_access.is_admin:
        members = members.filter(profile__trainer=for_access.user)

    members = list(members)
    last_visits = _last_visit_map(members)
    rows = []

    for member in members:
        profile = getattr(member, "profile", None)
        if profile is None or profile.membership_status == MembershipStatus.PAUSED:
            continue

        joined = profile.join_date
        # A member who joined three days ago hasn't gone quiet, they just
        # haven't been in yet.
        if joined and (on - joined).days < limits["grace_days"]:
            continue

        last = last_visits.get(member.id)
        last_date = timezone.localtime(last).date() if last else None
        # Someone who has never checked in is measured from the day they
        # joined, otherwise they could never become "quiet" at all.
        since = (on - (last_date or joined or on)).days

        if since < limits["cooling_days"]:
            continue

        payment = get_latest_completed_payment(member)
        rows.append(
            {
                "id": member.id,
                "username": member.username,
                "full_name": member.get_full_name(),
                "phone": profile.phone,
                "email": member.email,
                "trainer": profile.trainer.username if profile.trainer_id else None,
                "membership_status": profile.membership_status,
                "last_visit": last_date,
                "days_since_visit": since,
                "never_visited": last_date is None,
                "band": Band.QUIET if since >= limits["quiet_days"] else Band.COOLING,
                # Whether they are also about to lose their membership, which
                # changes the call from "we miss you" to "shall we renew you?".
                "expires_on": payment.period_end if payment else None,
                "days_left": (payment.period_end - on).days if payment else None,
            }
        )

    # Longest absence first: that is the order someone working a call list
    # actually wants, and it puts the people about to be lost at the top.
    rows.sort(key=lambda row: row["days_since_visit"], reverse=True)
    return rows


def summary(for_access=None, on=None):
    rows = at_risk(for_access=for_access, on=on)
    return {
        **thresholds(),
        "quiet": [r for r in rows if r["band"] == Band.QUIET],
        "cooling": [r for r in rows if r["band"] == Band.COOLING],
        "quiet_count": sum(1 for r in rows if r["band"] == Band.QUIET),
        "cooling_count": sum(1 for r in rows if r["band"] == Band.COOLING),
        "results": rows,
    }


def since_label(days):
    """Human wording for a gap, used by the digest email."""
    if days == 1:
        return "yesterday"
    return f"{days} days ago"


def stale_cutoff(days, on=None):
    """The date a visit would have to be older than to count as `days` quiet."""
    return (on or timezone.localdate()) - timedelta(days=days)
