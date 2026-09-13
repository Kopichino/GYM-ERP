from django.db import migrations


class Migration(migrations.Migration):
    """Instructor profiles are gone; a class now names the trainer's own account.

    The table goes, but this app and its migrations stay installed. Migrations
    elsewhere -- schedule_app's first one and two tenancy backfills -- were
    written against `instructors.Instructor` and name migrations here as
    dependencies. Removing the app would leave `migrate` unable to build its
    graph on any database that has already run them, which is every deployed one.
    """

    dependencies = [
        ("instructors", "0004_alter_instructor_tenant"),
        # The class-session foreign key has to be gone first, or the drop is refused.
        ("schedule_app", "0005_classsession_trainer"),
    ]

    operations = [
        migrations.DeleteModel(name="Instructor"),
    ]
