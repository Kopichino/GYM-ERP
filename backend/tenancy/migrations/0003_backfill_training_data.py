"""Assign the member-owned training tables to the founding branch.

These came later than the first backfill because their ownership was a product
decision rather than a mechanical one. Under a global `User`, a row's owner no
longer implies a gym: a member training at two gyms has one user account and
two histories, so `WorkoutSession.user` cannot answer "which gym was this?".

The split settled on:

* training data is tenant-scoped -- sets, measurements, goals, diet plans,
  badges and records are logged inside one gym's programme, and Gym A's work
  must not feed Gym B's leaderboards or badge progress;
* wearable data stays user-global -- a Fitbit token and a step count are about
  the person's body, not the building, and fragmenting them per gym would mean
  reconnecting the device once per membership.

Same guarantees as the first backfill: idempotent, fills nulls only, correct on
an empty database, and reversible without destroying anything.
"""

from django.db import migrations

TENANT_SCOPED = [
    ("workouts", "WorkoutSession"),
    ("workouts", "WorkoutLog"),
    ("bodystats", "BodyMeasurement"),
    ("bodystats", "MemberGoal"),
    ("nutrition", "DietPlan"),
    ("nutrition", "DietDay"),
    ("nutrition", "DietMeal"),
    ("gamification", "MemberBadge"),
    ("gamification", "PersonalRecord"),
    ("referrals", "Referral"),
]


def backfill(apps, schema_editor):
    Tenant = apps.get_model("tenancy", "Tenant")
    # The founding branch is the only one that can own pre-tenancy rows; if
    # somebody has already added a second, the oldest is still the right home
    # for data that predates both.
    tenant = Tenant.objects.order_by("id").first()
    if tenant is None:
        # Nothing to assign to, which means an empty install. The first
        # backfill creates the tenant, so this only happens when there is also
        # no data.
        return

    for app_label, model_name in TENANT_SCOPED:
        model = apps.get_model(app_label, model_name)
        model.objects.filter(tenant__isnull=True).update(tenant=tenant)


def unbackfill(apps, schema_editor):
    for app_label, model_name in TENANT_SCOPED:
        model = apps.get_model(app_label, model_name)
        model.objects.update(tenant=None)


class Migration(migrations.Migration):

    dependencies = [
        ("tenancy", "0002_backfill_the_founding_tenant"),
        ("workouts", "0005_workoutlog_tenant_workoutsession_tenant"),
        ("bodystats", "0002_bodymeasurement_tenant_membergoal_tenant"),
        ("nutrition", "0003_dietday_tenant_dietmeal_tenant_dietplan_tenant"),
        ("gamification", "0006_memberbadge_tenant_personalrecord_tenant"),
        ("referrals", "0004_referral_tenant"),
    ]

    operations = [
        migrations.RunPython(backfill, unbackfill),
    ]
