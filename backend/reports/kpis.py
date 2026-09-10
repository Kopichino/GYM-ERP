"""The handful of numbers an owner actually asks for.

Every one is computed from rows that already exist -- payments, check-ins,
bookings, availability. Nothing here is stored, so there is no month-end job to
forget to run and no cached figure that can disagree with the ledger it came
from.

Each metric returns its own definition alongside its value. "Churn" and "MRR"
mean different things at different gyms, and a number on a dashboard with no
statement of what it counts is worse than no number.
"""

from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Count, Q, Sum
from django.utils import timezone

from accounts.models import MembershipStatus, Role, User
from attendance.models import CheckInOut
from billing.models import Payment, PaymentStatus
from billing.services import get_latest_completed_payment
from schedule_app.models import BookingStatus, ClassBooking, ClassSession

TWO_DP = Decimal("0.01")
# Every plan is normalised to a month of this length so a yearly and a monthly
# membership can be added together honestly.
DAYS_IN_MONTH = Decimal("30")


def _money(value):
    return Decimal(value or 0).quantize(TWO_DP, rounding=ROUND_HALF_UP)


def active_members(on=None):
    """Members whose paid period covers `on`.

    Read off the ledger rather than `membership_status`, so a member whose
    profile has not been swept yet still counts correctly.
    """
    on = on or timezone.localdate()
    live = []
    for member in User.objects.filter(role=Role.MEMBER).select_related("profile"):
        payment = get_latest_completed_payment(member)
        if payment and payment.period_end >= on:
            live.append((member, payment))
    return live


def mrr(on=None):
    """Monthly recurring revenue.

    Each active membership contributes what it works out to per 30 days, so a
    14,000 yearly plan counts as ~1,150 a month rather than as 14,000 in the
    month it was sold. That is the number that tells an owner what the gym
    earns while nobody does anything.
    """
    on = on or timezone.localdate()
    total = Decimal("0")
    for _, payment in active_members(on):
        days = Decimal(max((payment.period_end - payment.period_start).days, 1))
        total += Decimal(payment.amount) / days * DAYS_IN_MONTH
    return _money(total)


def arpm(on=None):
    """Average revenue per member, per month. MRR spread over who is paying it."""
    live = active_members(on)
    if not live:
        return _money(0)
    return _money(mrr(on) / Decimal(len(live)))


def churn_rate(start, end, grace_days=7):
    """Share of members who lapsed in the window and did not come back.

    Same definition the churn report uses, so the dashboard and the report
    cannot disagree: last paid period ended inside the window, ended more than
    `grace_days` ago, and no later payment exists.
    """
    cutoff = timezone.localdate() - timedelta(days=grace_days)
    lapsed = 0
    considered = 0

    for member in User.objects.filter(role=Role.MEMBER):
        last = (
            Payment.objects.filter(member=member, status=PaymentStatus.COMPLETED)
            .order_by("-period_end")
            .first()
        )
        if last is None:
            continue
        # Anyone whose membership was live at any point in the window is part
        # of the population; otherwise the rate is measured against people who
        # had already left.
        if last.period_end < start:
            continue
        considered += 1
        if start <= last.period_end <= end and last.period_end < cutoff:
            lapsed += 1

    rate = (lapsed * 100 / considered) if considered else 0
    return {"lapsed": lapsed, "considered": considered, "rate": round(rate, 1)}


def pt_utilisation(start, end):
    """Booked PT hours against hours the trainers actually offered."""
    from pt.services import utilisation

    booked = offered = 0.0
    for trainer in User.objects.filter(role=Role.TRAINER):
        trainer_booked, trainer_offered = utilisation(trainer, start, end)
        booked += trainer_booked
        offered += trainer_offered

    rate = (booked * 100 / offered) if offered else 0
    return {"booked_hours": round(booked, 1), "offered_hours": round(offered, 1),
            "rate": round(rate, 1)}


def class_fill_rate(start, end):
    """Seats taken against seats offered, across classes in the window.

    Classes with no capacity set are left out of the rate entirely rather than
    treated as infinite or as zero -- an unlimited class cannot be more or less
    full, and including it either way would move the number for no reason.
    """
    sessions = ClassSession.objects.filter(
        date__gte=start, date__lte=end, capacity__isnull=False
    ).annotate(
        taken=Count("bookings", filter=Q(bookings__status__in=[
            BookingStatus.BOOKED, BookingStatus.ATTENDED
        ]))
    )

    seats = sum(session.capacity for session in sessions)
    taken = sum(session.taken for session in sessions)
    rate = (taken * 100 / seats) if seats else 0
    return {
        "sessions": len(sessions),
        "seats": seats,
        "booked": taken,
        "rate": round(rate, 1),
    }


def summary(start, end):
    """Everything the owner dashboard shows, in one pass."""
    on = min(end, timezone.localdate())
    live = active_members(on)
    collected = Payment.objects.filter(
        status=PaymentStatus.COMPLETED, paid_date__gte=start, paid_date__lte=end
    ).aggregate(total=Sum("amount"))["total"]

    visits = CheckInOut.objects.filter(
        check_in_time__date__gte=start, check_in_time__date__lte=end
    ).count()

    return {
        "from": start,
        "to": end,
        "active_members": len(live),
        "paused_members": User.objects.filter(
            role=Role.MEMBER, profile__membership_status=MembershipStatus.PAUSED
        ).count(),
        "mrr": str(mrr(on)),
        "arpm": str(arpm(on)),
        "collected": str(_money(collected)),
        "visits": visits,
        "churn": churn_rate(start, end),
        "pt": pt_utilisation(start, end),
        "classes": class_fill_rate(start, end),
        # Said out loud on the dashboard rather than left for someone to
        # assume, because each of these could reasonably mean something else.
        "definitions": {
            "mrr": "Each live membership's price spread over 30 days, added up.",
            "arpm": "MRR divided by the number of members it comes from.",
            "churn": (
                "Members whose last paid period ended in this window, more than "
                "7 days ago, with no later payment."
            ),
            "pt": "Booked one-to-one hours against the hours trainers offered.",
            "classes": "Seats taken against seats offered, ignoring classes with no cap.",
        },
    }
