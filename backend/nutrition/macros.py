"""Macro arithmetic for diet plans.

Every number a member sees -- a portion's calories, a meal's protein, a day's
total -- is worked out here from the grams on the plan and the macros on the
food. Nothing is written back. Correcting a food's calories therefore fixes
every plan that uses it, instead of leaving stale totals scattered around, which
is the same reasoning that keeps membership status derived from the ledger.
"""

from decimal import ROUND_HALF_UP, Decimal

ONE_DP = Decimal("0.1")
PER = Decimal("100")  # the catalogue is stored per 100 g

FIELDS = ("calories", "protein_g", "carbs_g", "fat_g")


def _round(value):
    return Decimal(value).quantize(ONE_DP, rounding=ROUND_HALF_UP)


def empty():
    return {field: Decimal("0.0") for field in FIELDS}


def for_portion(food, grams):
    """What `grams` of `food` contributes."""
    share = Decimal(grams) / PER
    return {field: _round(Decimal(getattr(food, field)) * share) for field in FIELDS}


def total(parts):
    """Sums any number of macro dicts. Rounding happens per portion, so a day's
    total is the sum of what the member actually reads next to each item --
    a total rounded separately would be off by a calorie or two and look wrong."""
    running = {field: Decimal("0.0") for field in FIELDS}
    for part in parts:
        for field in FIELDS:
            running[field] += Decimal(part[field])
    return {field: _round(running[field]) for field in FIELDS}


def for_meal(meal):
    return total(for_portion(item.food, item.quantity_g) for item in meal.items.all())


def for_day(day):
    return total(for_meal(meal) for meal in day.meals.all())


def for_plan(plan):
    """The plan's daily average, which is what a calorie target is compared
    against -- a weekly sum would mean nothing next to `target_calories`."""
    days = list(plan.days.all())
    if not days:
        return empty()
    summed = total(for_day(day) for day in days)
    count = Decimal(len(days))
    return {field: _round(Decimal(summed[field]) / count) for field in FIELDS}
