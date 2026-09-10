"""Derived body-composition figures.

Nothing here is written to the database. BMI, goal progress and trend deltas are
all computed from the rows that already exist, for the same reason membership
status is computed from the payment ledger: one source of truth cannot disagree
with itself.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

from .models import BodyMeasurement, GoalStatus, GoalType

# WHO adult BMI cut-offs.
BMI_BANDS = [
    (Decimal("18.5"), "underweight"),
    (Decimal("25"), "normal"),
    (Decimal("30"), "overweight"),
]
BMI_ABOVE_ALL = "obese"

TWO_DP = Decimal("0.01")
ONE_DP = Decimal("0.1")


def calculate_bmi(weight_kg, height_cm):
    """BMI in kg/m^2, or None when either input is missing."""
    if not weight_kg or not height_cm:
        return None
    height_m = Decimal(height_cm) / Decimal(100)
    if height_m <= 0:
        return None
    return (Decimal(weight_kg) / (height_m * height_m)).quantize(ONE_DP, rounding=ROUND_HALF_UP)


def bmi_category(bmi):
    if bmi is None:
        return None
    for ceiling, label in BMI_BANDS:
        if bmi < ceiling:
            return label
    return BMI_ABOVE_ALL


def latest_measurement(user):
    return BodyMeasurement.objects.filter(user=user).first()


def _monthly_visits(user):
    today = timezone.localdate()
    return user.check_ins.filter(
        check_in_time__year=today.year, check_in_time__month=today.month
    ).count()


def current_value_for(goal):
    """Where the member stands right now against `goal`."""
    if goal.goal_type == GoalType.WEIGHT:
        latest = latest_measurement(goal.user)
        return latest.weight_kg if latest else None
    if goal.goal_type == GoalType.BODY_FAT:
        latest = (
            BodyMeasurement.objects.filter(user=goal.user, body_fat_pct__isnull=False).first()
        )
        return latest.body_fat_pct if latest else None
    if goal.goal_type == GoalType.ATTENDANCE:
        return Decimal(_monthly_visits(goal.user))
    return goal.current_value


def goal_progress(goal):
    """0-100 percentage of the way from the starting point to the target.

    Works in either direction: losing weight and gaining it both count as
    progress as long as the member is moving toward the target. Without a
    baseline the only honest answers are 100 (reached) or 0 (not yet).
    """
    current = current_value_for(goal)
    if current is None:
        return None

    current = Decimal(current)
    target = Decimal(goal.target_value)
    start = Decimal(goal.start_value) if goal.start_value is not None else None

    if start is None or start == target:
        reached = current >= target if target >= (start or current) else current <= target
        return Decimal(100) if reached else Decimal(0)

    travelled = current - start
    distance = target - start
    pct = (travelled / distance) * Decimal(100)
    return max(Decimal(0), min(Decimal(100), pct)).quantize(TWO_DP, rounding=ROUND_HALF_UP)


def is_reached(goal):
    current = current_value_for(goal)
    if current is None:
        return False
    current, target = Decimal(current), Decimal(goal.target_value)
    start = Decimal(goal.start_value) if goal.start_value is not None else None
    # Direction of travel comes from the baseline; with none, assume the member
    # is climbing toward the target (visits, strength) rather than cutting.
    if start is not None and start > target:
        return current <= target
    return current >= target


def refresh_goal_status(goal):
    """Flip an active goal to achieved once its target is met. Archived and
    already-achieved goals are left alone -- reopening one is a person's call."""
    if goal.status != GoalStatus.ACTIVE or not is_reached(goal):
        return goal
    goal.status = GoalStatus.ACHIEVED
    goal.save(update_fields=["status", "updated_at"])
    return goal


def summary_for(user):
    """Everything the profile header and dashboard tile need in one payload."""
    measurements = BodyMeasurement.objects.filter(user=user)
    latest = measurements.first()
    earliest = measurements.order_by("recorded_on", "id").first()
    previous = measurements[1] if measurements.count() > 1 else None

    height_cm = getattr(getattr(user, "profile", None), "height_cm", None)
    weight = latest.weight_kg if latest else None
    bmi = calculate_bmi(weight, height_cm)

    def delta(against):
        if not latest or not against or against.pk == latest.pk:
            return None
        return (latest.weight_kg - against.weight_kg).quantize(TWO_DP)

    return {
        "height_cm": height_cm,
        "weight_kg": weight,
        "body_fat_pct": latest.body_fat_pct if latest else None,
        "recorded_on": latest.recorded_on if latest else None,
        "bmi": bmi,
        "bmi_category": bmi_category(bmi),
        "change_since_previous": delta(previous),
        "change_since_start": delta(earliest),
        "measurement_count": measurements.count(),
    }
