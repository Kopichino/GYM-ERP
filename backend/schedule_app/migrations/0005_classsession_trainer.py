import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def copy_instructor_to_trainer(apps, schema_editor):
    """Carry each class's trainer across before the instructor link goes.

    A class whose instructor profile was linked to a login keeps that person. A
    content-only profile -- a guest with no account -- has nobody to carry, so
    that class ends up with no trainer, which is what members already saw for
    anyone without a profile.
    """
    ClassSession = apps.get_model("schedule_app", "ClassSession")
    sessions = ClassSession.objects.exclude(instructor__isnull=True).select_related("instructor")
    for session in sessions:
        if session.instructor.user_id:
            session.trainer_id = session.instructor.user_id
            session.save(update_fields=["trainer"])


class Migration(migrations.Migration):

    dependencies = [
        ("schedule_app", "0004_alter_classbooking_tenant_alter_classsession_tenant"),
        ("instructors", "0004_alter_instructor_tenant"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="classsession",
            name="trainer",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="classes_run",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(copy_instructor_to_trainer, migrations.RunPython.noop),
        migrations.RemoveField(model_name="classsession", name="instructor"),
    ]
