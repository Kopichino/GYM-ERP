"""Report aggregation.

Nothing here stores a figure. Every number is computed from the ledgers that
already exist -- payments, check-ins, expenses, commission entries -- so a
report can never disagree with the screen it summarises.
"""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from accounts.models import Role, User
from attendance.models import CheckInOut
from billing.models import Payment, PaymentStatus
from commissions.models import CommissionEntry, EntryStatus
from expenses.models import Expense


def _window(start, end):
    end = end or timezone.localdate()
    start = start or (end - timedelta(days=29))
    return start, end


def revenue(start=None, end=None):
    """Money in, money out, and what's left."""
    start, end = _window(start, end)
    payments = Payment.objects.filter(
        status=PaymentStatus.COMPLETED, paid_date__gte=start, paid_date__lte=end
    )
    costs = Expense.objects.filter(spent_on__gte=start, spent_on__lte=end)

    collected = payments.aggregate(t=Sum("amount"))["t"] or Decimal("0")
    discounts = payments.aggregate(t=Sum("discount_amount"))["t"] or Decimal("0")
    spent = costs.aggregate(t=Sum("amount"))["t"] or Decimal("0")

    by_month = (
        payments.annotate(month=TruncMonth("paid_date"))
        .values("month")
        .annotate(total=Sum("amount"), count=Count("id"))
        .order_by("month")
    )
    by_plan = (
        payments.values("plan__name")
        .annotate(total=Sum("amount"), count=Count("id"))
        .order_by("-total")
    )
    by_method = (
        payments.values("method").annotate(total=Sum("amount")).order_by("-total")
    )

    return {
        "start": start,
        "end": end,
        "collected": collected,
        "discounts_given": discounts,
        # What the sales would have been worth at list price.
        "gross": collected + discounts,
        "expenses": spent,
        "net": collected - spent,
        "payment_count": payments.count(),
        "by_month": [
            {"month": r["month"], "total": r["total"], "count": r["count"]} for r in by_month
        ],
        "by_plan": [
            {"plan": r["plan__name"], "total": r["total"], "count": r["count"]} for r in by_plan
        ],
        "by_method": [{"method": r["method"], "total": r["total"]} for r in by_method],
    }


def attendance(start=None, end=None):
    start, end = _window(start, end)
    visits = CheckInOut.objects.filter(
        check_in_time__date__gte=start, check_in_time__date__lte=end
    )

    by_day = (
        visits.values("check_in_time__date")
        .annotate(count=Count("id"))
        .order_by("check_in_time__date")
    )
    by_method = visits.values("method").annotate(count=Count("id")).order_by("-count")

    # Busiest hour tells the gym when to staff the floor.
    by_hour = {}
    for stamp in visits.values_list("check_in_time", flat=True):
        hour = timezone.localtime(stamp).hour
        by_hour[hour] = by_hour.get(hour, 0) + 1

    active_members = User.objects.filter(role=Role.MEMBER).count()
    unique = visits.values("user").distinct().count()

    return {
        "start": start,
        "end": end,
        "total_visits": visits.count(),
        "unique_members": unique,
        "member_count": active_members,
        # What share of the membership showed up at all in the window.
        "participation_pct": round(unique / active_members * 100, 1) if active_members else 0,
        "by_day": [
            {"date": r["check_in_time__date"], "count": r["count"]} for r in by_day
        ],
        "by_method": [{"method": r["method"], "count": r["count"]} for r in by_method],
        "by_hour": [{"hour": h, "count": by_hour[h]} for h in sorted(by_hour)],
    }


def churn(start=None, end=None, grace_days=7):
    """Who lapsed and didn't come back.

    'Churned' here means: their last paid period ended inside the window and
    more than `grace_days` ago, and no later payment exists. The gym never
    records an intent to leave, so this is the honest definition available --
    it is stated on screen rather than left implied.
    """
    start, end = _window(start, end)
    cutoff = timezone.localdate() - timedelta(days=grace_days)

    lapsed, retained = [], 0
    for member in User.objects.filter(role=Role.MEMBER).select_related("profile"):
        last = (
            Payment.objects.filter(member=member, status=PaymentStatus.COMPLETED)
            .order_by("-period_end")
            .first()
        )
        if last is None:
            continue
        if start <= last.period_end <= end and last.period_end < cutoff:
            lapsed.append(
                {
                    "member": member.username,
                    "name": member.get_full_name() or member.username,
                    "expired_on": last.period_end,
                    "days_lapsed": (timezone.localdate() - last.period_end).days,
                    "last_plan": last.plan.name,
                }
            )
        elif last.period_end >= cutoff:
            retained += 1

    total = len(lapsed) + retained
    return {
        "start": start,
        "end": end,
        "grace_days": grace_days,
        "definition": (
            "A member whose last paid period ended in this window and more than "
            f"{grace_days} days ago, with no renewal since."
        ),
        "churned_count": len(lapsed),
        "retained_count": retained,
        "churn_rate_pct": round(len(lapsed) / total * 100, 1) if total else 0,
        "members": sorted(lapsed, key=lambda m: m["expired_on"], reverse=True),
    }


def pt_performance(start=None, end=None):
    """Per-trainer: roster size, sessions coached, revenue attributed, and what
    they earned from it."""
    start, end = _window(start, end)
    rows = []

    for trainer in User.objects.filter(role=Role.TRAINER):
        members = User.objects.filter(profile__trainer=trainer)
        member_ids = list(members.values_list("id", flat=True))

        payments = Payment.objects.filter(
            member_id__in=member_ids,
            status=PaymentStatus.COMPLETED,
            paid_date__gte=start,
            paid_date__lte=end,
        )
        entries = CommissionEntry.objects.filter(
            trainer=trainer, earned_on__gte=start, earned_on__lte=end
        ).exclude(status=EntryStatus.VOID)
        visits = CheckInOut.objects.filter(
            user_id__in=member_ids,
            check_in_time__date__gte=start,
            check_in_time__date__lte=end,
        )

        rows.append(
            {
                "trainer": trainer.username,
                "name": trainer.get_full_name() or trainer.username,
                "member_count": len(member_ids),
                "revenue": payments.aggregate(t=Sum("amount"))["t"] or Decimal("0"),
                "payment_count": payments.count(),
                "commission": entries.aggregate(t=Sum("amount"))["t"] or Decimal("0"),
                "member_visits": visits.count(),
            }
        )

    return {
        "start": start,
        "end": end,
        "trainers": sorted(rows, key=lambda r: r["revenue"], reverse=True),
    }
