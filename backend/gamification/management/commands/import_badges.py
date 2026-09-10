"""Loads a starter badge ladder.

Deliberately shipped **without artwork** -- every badge is created with an empty
image so the gym can upload its own from Admin -> Badges. Until then the portal
draws a tier-coloured placeholder rather than a broken image.

Five tiers per criterion, so a badge set has somewhere to grow into without the
thresholds inflating. Safe to re-run: existing badges are left alone.
"""

from django.core.management.base import BaseCommand

from gamification.models import Badge, Criterion, Tier
from workouts.models import Exercise

# criterion, (tier, code, name, threshold, description)
LADDERS = [
    (
        Criterion.VISITS,
        [
            (Tier.BRONZE, "visits-10", "Regular", 10, "Ten visits to the gym."),
            (Tier.SILVER, "visits-50", "Committed", 50, "Fifty visits."),
            (Tier.GOLD, "visits-150", "Fixture", 150, "A hundred and fifty visits."),
            (Tier.PLATINUM, "visits-300", "Cornerstone", 300, "Three hundred visits."),
            (Tier.ELITE, "visits-500", "Institution", 500, "Five hundred visits."),
        ],
    ),
    (
        Criterion.STREAK,
        [
            (Tier.BRONZE, "streak-3", "Rolling", 3, "Three days in a row."),
            (Tier.SILVER, "streak-7", "Full Week", 7, "Seven days in a row."),
            (Tier.GOLD, "streak-14", "Fortnight", 14, "Fourteen days in a row."),
            (Tier.PLATINUM, "streak-30", "Unbroken", 30, "Thirty days in a row."),
            (Tier.ELITE, "streak-60", "Relentless", 60, "Sixty days in a row."),
        ],
    ),
    (
        Criterion.WORKOUTS,
        [
            (Tier.BRONZE, "workouts-5", "Getting Started", 5, "Five workouts logged."),
            (Tier.SILVER, "workouts-25", "In the Habit", 25, "Twenty-five workouts logged."),
            (Tier.GOLD, "workouts-75", "Serious", 75, "Seventy-five workouts logged."),
            (Tier.PLATINUM, "workouts-200", "Devoted", 200, "Two hundred workouts logged."),
            (Tier.ELITE, "workouts-400", "Lifetime", 400, "Four hundred workouts logged."),
        ],
    ),
    (
        Criterion.SETS,
        [
            (Tier.BRONZE, "sets-50", "Volume I", 50, "Fifty sets logged."),
            (Tier.SILVER, "sets-250", "Volume II", 250, "Two hundred and fifty sets."),
            (Tier.GOLD, "sets-1000", "Volume III", 1000, "A thousand sets."),
            (Tier.PLATINUM, "sets-2500", "Volume IV", 2500, "Two and a half thousand sets."),
            (Tier.ELITE, "sets-5000", "Volume V", 5000, "Five thousand sets."),
        ],
    ),
    (
        Criterion.RECORDS,
        [
            (Tier.BRONZE, "records-1", "First Record", 1, "Your first personal record."),
            (Tier.SILVER, "records-10", "Climbing", 10, "Ten personal records."),
            (Tier.GOLD, "records-30", "Stronger", 30, "Thirty personal records."),
            (Tier.PLATINUM, "records-75", "Peak Form", 75, "Seventy-five personal records."),
            (Tier.ELITE, "records-150", "Record Breaker", 150, "A hundred and fifty records."),
        ],
    ),
    (
        Criterion.MONTHS,
        [
            (Tier.BRONZE, "months-1", "One Month In", 1, "A month as a member."),
            (Tier.SILVER, "months-6", "Half a Year", 6, "Six months as a member."),
            (Tier.GOLD, "months-12", "One Year", 12, "A year as a member."),
            (Tier.PLATINUM, "months-24", "Two Years", 24, "Two years as a member."),
            (Tier.ELITE, "months-60", "Five Years", 60, "Five years as a member."),
        ],
    ),
    (
        Criterion.CLASSES,
        [
            (Tier.BRONZE, "classes-5", "Joined In", 5, "Five classes attended."),
            (Tier.SILVER, "classes-25", "Class Act", 25, "Twenty-five classes attended."),
            (Tier.GOLD, "classes-50", "Front Row", 50, "Fifty classes attended."),
            (Tier.PLATINUM, "classes-150", "Regular Fixture", 150, "A hundred and fifty classes."),
            (Tier.ELITE, "classes-300", "Part of the Furniture", 300, "Three hundred classes."),
        ],
    ),
    (
        # Months in a row that were trained in. A *daily* streak long enough to
        # mean "kept it up for half a year" is not something anybody does, so
        # the long-haul milestones are measured this way instead.
        Criterion.MONTH_STREAK,
        [
            (Tier.BRONZE, "monthstreak-3", "Three Months Running", 3, "Three months in a row with a visit."),
            (Tier.SILVER, "monthstreak-6", "Six Months Running", 6, "Six months in a row with a visit."),
            (Tier.GOLD, "monthstreak-12", "A Year Unbroken", 12, "Twelve months in a row with a visit."),
            (Tier.PLATINUM, "monthstreak-24", "Two Years Unbroken", 24, "Twenty-four months in a row."),
            (Tier.ELITE, "monthstreak-36", "Three Years Unbroken", 36, "Thirty-six months in a row."),
        ],
    ),
]

# Lift milestones, which need an exercise as well as a number: "100kg" is one
# achievement on the squat and a completely different one on the press. Matched
# by exercise *name*, and quietly skipped when the gym's catalogue does not have
# that lift -- a badge nobody can ever earn is worse than a missing one.
LIFT_LADDERS = [
    (
        "Barbell Back Squat",
        [
            (Tier.BRONZE, "squat-60", "Sixty Squat", 60, "A 60kg barbell back squat."),
            (Tier.SILVER, "squat-100", "Hundred Squat", 100, "A 100kg barbell back squat."),
            (Tier.GOLD, "squat-140", "Heavy Squat", 140, "A 140kg barbell back squat."),
            (Tier.PLATINUM, "squat-180", "Serious Squat", 180, "A 180kg barbell back squat."),
            (Tier.ELITE, "squat-220", "Elite Squat", 220, "A 220kg barbell back squat."),
        ],
    ),
    (
        "Barbell Bench Press",
        [
            (Tier.BRONZE, "bench-40", "Forty Bench", 40, "A 40kg barbell bench press."),
            (Tier.SILVER, "bench-70", "Seventy Bench", 70, "A 70kg barbell bench press."),
            (Tier.GOLD, "bench-100", "Hundred Bench", 100, "A 100kg barbell bench press."),
            (Tier.PLATINUM, "bench-140", "Serious Bench", 140, "A 140kg barbell bench press."),
            (Tier.ELITE, "bench-170", "Elite Bench", 170, "A 170kg barbell bench press."),
        ],
    ),
    (
        "Deadlift",
        [
            (Tier.BRONZE, "deadlift-80", "Eighty Pull", 80, "An 80kg deadlift."),
            (Tier.SILVER, "deadlift-120", "Hundred-Twenty Pull", 120, "A 120kg deadlift."),
            (Tier.GOLD, "deadlift-180", "Heavy Pull", 180, "A 180kg deadlift."),
            (Tier.PLATINUM, "deadlift-220", "Serious Pull", 220, "A 220kg deadlift."),
            (Tier.ELITE, "deadlift-260", "Elite Pull", 260, "A 260kg deadlift."),
        ],
    ),
]


class Command(BaseCommand):
    help = "Load the starter badge ladder (no artwork -- upload your own later)."

    def handle(self, *args, **options):
        created = 0
        for criterion, rungs in LADDERS:
            for tier, code, name, threshold, description in rungs:
                _, was_created = Badge.objects.get_or_create(
                    code=code,
                    defaults={
                        "name": name,
                        "description": description,
                        "tier": tier,
                        "criterion": criterion,
                        "threshold": threshold,
                        # image intentionally left unset.
                    },
                )
                created += was_created

        skipped = []
        for exercise_name, rungs in LIFT_LADDERS:
            exercise = Exercise.objects.filter(name__iexact=exercise_name).first()
            if exercise is None:
                skipped.append(exercise_name)
                continue
            for tier, code, name, threshold, description in rungs:
                _, was_created = Badge.objects.get_or_create(
                    code=code,
                    defaults={
                        "name": name,
                        "description": description,
                        "tier": tier,
                        "criterion": Criterion.LIFT,
                        "exercise": exercise,
                        "threshold": threshold,
                    },
                )
                created += was_created

        if skipped:
            self.stdout.write(
                self.style.WARNING(
                    "No lift badges for: "
                    + ", ".join(skipped)
                    + " -- not in the exercise catalogue."
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Badges: {created} added, {Badge.objects.count()} total. "
                "Artwork is empty -- upload it from Admin > Badges."
            )
        )
