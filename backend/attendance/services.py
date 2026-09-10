"""The single place a visit is opened or closed.

Every entry route -- the dashboard button, a QR scan, a fingerprint terminal --
comes through here, so the "one open check-in per user" rule is enforced once.
The rule itself is a partial unique index on the model; this module catches the
race rather than pretending an application-level check is sufficient.
"""

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import CheckInMethod, CheckInOut


class AttendanceError(Exception):
    """A check-in/out that cannot proceed, with a member-readable reason."""


def open_visit(user, method=CheckInMethod.TAP):
    if CheckInOut.objects.filter(user=user, check_out_time__isnull=True).exists():
        raise AttendanceError("Already checked in.")
    try:
        with transaction.atomic():
            return CheckInOut.objects.create(user=user, method=method)
    except IntegrityError:
        # Two taps raced past the check above; the DB constraint is the real
        # source of truth, so treat losing the race as "already checked in".
        raise AttendanceError("Already checked in.")


def close_visit(user):
    record = CheckInOut.objects.filter(user=user, check_out_time__isnull=True).first()
    if not record:
        raise AttendanceError("No open check-in to close.")
    record.check_out_time = timezone.now()
    record.save(update_fields=["check_out_time"])
    return record


def toggle_visit(user, method=CheckInMethod.TAP):
    """What a turnstile or terminal does: one punch in, one punch out.

    Returns (record, action) where action is "in" or "out". A device has no way
    to know which the member meant, so the open visit decides.
    """
    open_record = CheckInOut.objects.filter(user=user, check_out_time__isnull=True).first()
    if open_record:
        return close_visit(user), "out"
    return open_visit(user, method=method), "in"


def visit_dates(user):
    """Every calendar day the member was in, deduped and sorted.

    Local days, not UTC ones: a 22:00 check-in belongs to the evening the
    member trained, and counting it as the next day would break their streak
    for no reason they could see.
    """
    stamps = CheckInOut.objects.filter(user=user).values_list("check_in_time", flat=True)
    return sorted({timezone.localtime(stamp).date() for stamp in stamps})


def streaks(user, dates=None):
    """(current, longest) run of consecutive days.

    Shared by the consistency calendar and the badge criteria so the number a
    member sees on their dashboard is the same one their badge was awarded
    against -- two implementations of "streak" would eventually disagree.

    Today not being in the list doesn't end a run: a member who trained
    yesterday and hasn't been in yet today still has their streak. It ends on
    the first full day missed.
    """
    dates = visit_dates(user) if dates is None else dates
    if not dates:
        return 0, 0

    run = longest = 1
    for previous, current in zip(dates, dates[1:]):
        run = run + 1 if (current - previous).days == 1 else 1
        longest = max(longest, run)

    gap = (timezone.localdate() - dates[-1]).days
    return (run if gap <= 1 else 0), longest


def toggle_guest_visit(day_pass):
    """A day-pass guest arriving or leaving.

    Kept as its own function rather than widening `toggle_visit`: the member
    path is the one every other feature depends on, and adding a branch to it
    to serve walk-ins would put guest logic in front of every member check-in.
    The rule is the same though -- one open visit at a time, enforced by its
    own partial unique index rather than by this check.
    """
    open_record = CheckInOut.objects.filter(
        day_pass=day_pass, check_out_time__isnull=True
    ).first()
    if open_record:
        open_record.check_out_time = timezone.now()
        open_record.save(update_fields=["check_out_time"])
        return open_record, "out"

    try:
        with transaction.atomic():
            record = CheckInOut.objects.create(
                day_pass=day_pass, method=CheckInMethod.MANUAL
            )
    except IntegrityError:
        # Two front-desk taps raced; the index decided.
        raise AttendanceError("That pass is already checked in.")
    return record, "in"


def occupancy(start, end):
    """How busy the gym is, by weekday and hour.

    Counts visits, not people: someone who comes twice on a Tuesday is two
    Tuesday visits, which is what the question "how busy is Tuesday morning?"
    actually means.

    Guests are included. Their visits live in this table precisely so footfall
    figures cover the whole gym rather than only the members in it.

    Local hours, not UTC ones -- a 19:00 session belongs to the evening it
    happened in, and bucketing it by UTC would move the gym's peak by however
    far it sits from Greenwich.
    """
    stamps = CheckInOut.objects.filter(
        check_in_time__date__gte=start, check_in_time__date__lte=end
    ).values_list("check_in_time", flat=True)

    # weekday (0 = Monday) -> hour -> count
    grid = [[0] * 24 for _ in range(7)]
    total = 0
    for stamp in stamps:
        local = timezone.localtime(stamp)
        grid[local.weekday()][local.hour] += 1
        total += 1

    busiest = None
    if total:
        weekday, hour = max(
            ((w, h) for w in range(7) for h in range(24)),
            key=lambda cell: grid[cell[0]][cell[1]],
        )
        if grid[weekday][hour]:
            busiest = {"weekday": weekday, "hour": hour, "visits": grid[weekday][hour]}

    return {
        "from": start,
        "to": end,
        "total_visits": total,
        "peak": max((count for row in grid for count in row), default=0),
        "busiest": busiest,
        "grid": grid,
    }
