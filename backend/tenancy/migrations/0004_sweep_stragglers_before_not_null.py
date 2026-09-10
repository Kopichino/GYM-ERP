"""Catch rows written after the backfill but before the columns became required.

There is a window between the two: the backfill runs, the deploy continues, and
the application keeps taking traffic. Every visit recorded, payment taken or
enquiry logged in that window is written by code that predates the stamping
signal, so it lands with a null tenant -- and the NOT NULL migration then fails
on it. Exactly that happened here, on a single check-in.

`run_before` puts this immediately ahead of every NOT NULL alteration rather
than relying on migration-name ordering, so no app can be altered before its
stragglers have been swept.

Assigns to the oldest tenant, which is the founding one. That is only correct
because these rows predate multi-tenancy having any second gym to confuse them
with -- if a platform already has several gyms, a null tenant is genuinely
ambiguous and the sweep would be guessing. So it refuses to guess: with more
than one tenant present it raises rather than filing rows under the wrong gym.
"""

from django.db import migrations

# (app label, model) for everything that gained a tenancy FK.
SCOPED = [
    ("announcements", "Announcement", "tenant"),
    ("attendance", "CheckInOut", "tenant"),
    ("billing", "Payment", "tenant"),
    ("billing", "PaymentOrder", "tenant"),
    ("billing", "DayPass", "tenant"),
    ("billing", "Plan", "organisation"),
    ("billing", "Discount", "organisation"),
    ("bodystats", "BodyMeasurement", "tenant"),
    ("bodystats", "MemberGoal", "tenant"),
    ("branding", "Branding", "organisation"),
    ("commissions", "CommissionRule", "organisation"),
    ("commissions", "Payout", "tenant"),
    ("commissions", "CommissionEntry", "tenant"),
    ("crm", "Enquiry", "tenant"),
    ("crm", "EnquiryNote", "tenant"),
    ("crm", "RetentionPolicy", "organisation"),
    ("devices", "Device", "tenant"),
    ("devices", "DeviceEvent", "tenant"),
    ("expenses", "Expense", "tenant"),
    ("expenses", "ExpenseCategory", "organisation"),
    ("feedback", "Survey", "organisation"),
    ("feedback", "SurveyResponse", "tenant"),
    ("gallery", "GalleryPost", "tenant"),
    ("gamification", "Badge", "organisation"),
    ("gamification", "MemberBadge", "tenant"),
    ("gamification", "PersonalRecord", "tenant"),
    ("instructors", "Instructor", "tenant"),
    ("invoicing", "Invoice", "tenant"),
    ("invoicing", "InvoiceCounter", "tenant"),
    ("messaging", "Message", "tenant"),
    ("notifications", "NotificationLog", "tenant"),
    ("nutrition", "DietPlan", "tenant"),
    ("nutrition", "DietDay", "tenant"),
    ("nutrition", "DietMeal", "tenant"),
    ("pt", "Availability", "tenant"),
    ("pt", "Unavailable", "tenant"),
    ("pt", "PTSession", "tenant"),
    ("referrals", "Referral", "tenant"),
    ("referrals", "ReferralProgram", "organisation"),
    ("reports", "SavedReport", "tenant"),
    ("schedule_app", "ClassSession", "tenant"),
    ("schedule_app", "ClassBooking", "tenant"),
    ("shifts", "Shift", "tenant"),
    ("workouts", "WorkoutSession", "tenant"),
    ("workouts", "WorkoutLog", "tenant"),
]


def sweep(apps, schema_editor):
    Tenant = apps.get_model("tenancy", "Tenant")
    tenants = list(Tenant.objects.order_by("id")[:2])
    if not tenants:
        return  # Empty install: nothing written, nothing to assign.

    if len(tenants) > 1:
        # More than one gym exists, so "which gym does this orphan belong to"
        # has no safe answer. Better to stop the deploy than to file a
        # member's visit under a gym they have never been to.
        stragglers = {}
        for app_label, model_name, field in SCOPED:
            model = apps.get_model(app_label, model_name)
            count = model.objects.filter(**{f"{field}__isnull": True}).count()
            if count:
                stragglers[f"{app_label}.{model_name}"] = count
        if stragglers:
            raise RuntimeError(
                "Rows with no tenant remain and this platform has more than one "
                f"gym, so they cannot be assigned safely: {stragglers}. Assign "
                "them explicitly, then re-run the migration."
            )
        return

    founding = tenants[0]
    for app_label, model_name, field in SCOPED:
        model = apps.get_model(app_label, model_name)
        value = founding if field == "tenant" else founding.organisation
        model.objects.filter(**{f"{field}__isnull": True}).update(**{field: value})


class Migration(migrations.Migration):

    dependencies = [("tenancy", "0003_backfill_training_data")]

    # Ahead of every NOT NULL alteration, so none of them can meet a null.
    run_before = [
        ("announcements", "0003_alter_announcement_tenant"),
        ("attendance", "0005_alter_checkinout_tenant"),
        ("billing", "0007_alter_daypass_tenant_alter_discount_organisation_and_more"),
        ("bodystats", "0003_alter_bodymeasurement_tenant_alter_membergoal_tenant"),
        ("branding", "0004_alter_branding_organisation"),
        ("commissions", "0003_alter_commissionentry_tenant_and_more"),
        ("crm", "0006_alter_enquiry_tenant_alter_enquirynote_tenant_and_more"),
        ("devices", "0004_alter_device_tenant_alter_deviceevent_tenant"),
        ("expenses", "0004_alter_expense_tenant_and_more"),
        ("feedback", "0004_alter_survey_organisation_and_more"),
        ("gallery", "0003_alter_gallerypost_tenant"),
        ("gamification", "0007_alter_badge_organisation_alter_memberbadge_tenant_and_more"),
        ("instructors", "0004_alter_instructor_tenant"),
        ("invoicing", "0004_alter_invoice_tenant_alter_invoicecounter_tenant"),
        ("messaging", "0003_alter_message_tenant"),
        ("notifications", "0003_alter_notificationlog_tenant"),
        ("nutrition", "0004_alter_dietday_tenant_alter_dietmeal_tenant_and_more"),
        ("pt", "0003_alter_availability_tenant_alter_ptsession_tenant_and_more"),
        ("referrals", "0005_alter_referral_tenant_and_more"),
        ("reports", "0003_alter_savedreport_tenant"),
        ("schedule_app", "0004_alter_classbooking_tenant_alter_classsession_tenant"),
        ("shifts", "0003_alter_shift_tenant"),
        ("workouts", "0006_alter_workoutlog_tenant_alter_workoutsession_tenant"),
    ]

    operations = [migrations.RunPython(sweep, migrations.RunPython.noop)]
