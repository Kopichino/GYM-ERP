"""Point every existing row at the gym this system was originally built for.

Before multi-tenancy there was exactly one gym, implied by the whole database.
This makes that gym explicit: one Organisation, one Tenant under it, and every
operational row assigned to it.

Written to be safe on a live database:

* **Idempotent.** Every step is get_or_create or a filtered update on rows that
  are still null, so a re-run after a partial failure finishes the job rather
  than creating a second gym.
* **Non-destructive.** It only fills nulls. No row is deleted, and no non-null
  value is ever overwritten.
* **Correct on an empty database.** A fresh install has no rows to backfill and
  simply ends up with the founding tenant ready for use.

The identity is taken from the existing Branding row when there is one, so the
gym keeps its own name rather than being renamed "Default" by a migration.

Reversing this deliberately does not delete the tenant. Dropping an
Organisation that rows now point at would cascade, and a migration that can
silently destroy a production gym's data is not one worth having.
"""

from django.db import migrations
from django.utils.text import slugify

#: (app label, model name, FK field) for every table the backfill touches.
ORG_SCOPED = [
    ("billing", "Plan"),
    ("billing", "Discount"),
    ("expenses", "ExpenseCategory"),
    ("commissions", "CommissionRule"),
    ("crm", "RetentionPolicy"),
    ("referrals", "ReferralProgram"),
    ("feedback", "Survey"),
    ("gamification", "Badge"),
    ("branding", "Branding"),
]

TENANT_SCOPED = [
    ("attendance", "CheckInOut"),
    ("billing", "Payment"),
    ("billing", "PaymentOrder"),
    ("billing", "DayPass"),
    ("invoicing", "InvoiceCounter"),
    ("invoicing", "Invoice"),
    ("expenses", "Expense"),
    ("crm", "Enquiry"),
    ("crm", "EnquiryNote"),
    ("announcements", "Announcement"),
    ("instructors", "Instructor"),
    ("gallery", "GalleryPost"),
    ("schedule_app", "ClassSession"),
    ("schedule_app", "ClassBooking"),
    ("shifts", "Shift"),
    ("pt", "Availability"),
    ("pt", "Unavailable"),
    ("pt", "PTSession"),
    ("messaging", "Message"),
    ("notifications", "NotificationLog"),
    ("reports", "SavedReport"),
    ("commissions", "Payout"),
    ("commissions", "CommissionEntry"),
    ("devices", "Device"),
    ("devices", "DeviceEvent"),
    ("feedback", "SurveyResponse"),
]


def founding_identity(apps):
    """The gym's own name, if it ever configured one."""
    Branding = apps.get_model("branding", "Branding")
    row = Branding.objects.filter(is_active=True).order_by("-updated_at").first()
    if row and row.name:
        return row.name
    return "Default Gym"


def backfill(apps, schema_editor):
    Organisation = apps.get_model("tenancy", "Organisation")
    Tenant = apps.get_model("tenancy", "Tenant")
    Membership = apps.get_model("tenancy", "Membership")
    User = apps.get_model("accounts", "User")

    name = founding_identity(apps)
    slug = slugify(name)[:60] or "default"

    org, _ = Organisation.objects.get_or_create(
        slug=slug, defaults={"name": name}
    )
    # "main" as the branch slug: a single-site gym has one branch and calling it
    # anything cleverer would only have to be explained later.
    tenant, _ = Tenant.objects.get_or_create(
        slug=f"{slug}-main"[:60],
        defaults={"organisation": org, "name": name},
    )

    for app_label, model_name in ORG_SCOPED:
        model = apps.get_model(app_label, model_name)
        model.objects.filter(organisation__isnull=True).update(organisation=org)

    for app_label, model_name in TENANT_SCOPED:
        model = apps.get_model(app_label, model_name)
        model.objects.filter(tenant__isnull=True).update(tenant=tenant)

    # Every existing account becomes a member of the founding branch, holding
    # the role it already had on the user row. This is the whole point of the
    # migration for auth: `User.role` is about to stop being the source of
    # truth, and this is what carries its meaning across before it does.
    for user in User.objects.all().iterator():
        Membership.objects.get_or_create(
            user=user,
            tenant=tenant,
            role=user.role,
            defaults={"starts_on": user.date_joined.date()},
        )


def unbackfill(apps, schema_editor):
    """Clear the FKs but leave the tenant standing.

    Deleting the Organisation would cascade into every row just re-nulled, so
    reversing this migration undoes the assignment and nothing else. The empty
    tenant is harmless; a destroyed gym is not.
    """
    for app_label, model_name in ORG_SCOPED:
        model = apps.get_model(app_label, model_name)
        model.objects.update(organisation=None)
    for app_label, model_name in TENANT_SCOPED:
        model = apps.get_model(app_label, model_name)
        model.objects.update(tenant=None)


class Migration(migrations.Migration):

    dependencies = [
        ("tenancy", "0001_initial"),
        ("accounts", "0001_initial"),
        ("attendance", "0004_checkinout_tenant"),
        ("billing", "0005_daypass_tenant_discount_organisation_payment_tenant_and_more"),
        ("invoicing", "0002_invoice_tenant_invoicecounter_tenant"),
        ("expenses", "0002_expense_tenant_expensecategory_organisation"),
        ("crm", "0004_enquiry_tenant_enquirynote_tenant_and_more"),
        ("announcements", "0002_announcement_tenant"),
        ("instructors", "0003_instructor_tenant"),
        ("gallery", "0002_gallerypost_tenant"),
        ("schedule_app", "0003_classbooking_tenant_classsession_tenant"),
        ("shifts", "0002_shift_tenant"),
        ("pt", "0002_availability_tenant_ptsession_tenant_and_more"),
        ("messaging", "0002_message_tenant"),
        ("notifications", "0002_notificationlog_tenant"),
        ("reports", "0002_savedreport_tenant"),
        ("commissions", "0002_commissionentry_tenant_commissionrule_organisation_and_more"),
        ("devices", "0003_device_tenant_deviceevent_tenant"),
        ("feedback", "0002_survey_organisation_surveyresponse_tenant"),
        ("referrals", "0002_referralprogram_organisation"),
        ("gamification", "0004_badge_organisation"),
        ("branding", "0002_branding_organisation"),
    ]

    operations = [
        migrations.RunPython(backfill, unbackfill),
    ]
