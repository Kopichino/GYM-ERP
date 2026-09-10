"""Drop the tables the removed `wearables` app left behind.

Deleting an app removes its code and its migrations, but not its tables -- and
because the migrations went with it, there is no longer anywhere in that app to
put a `DeleteModel`. So the cleanup lives in `core`, which is the shared app and
outlives every feature.

The `django_migrations` rows go too. Django ignores rows for apps it no longer
knows about, so leaving them is harmless right up until someone adds an app
called `wearables` again and finds its first migration already recorded as
applied against tables that do not exist.

Irreversible on purpose. The reverse of this is not "recreate two empty
tables" -- it is restoring an entire feature, which is a code change rather
than a schema one, and pretending otherwise would let `migrate` roll back to a
state the codebase cannot serve.
"""

from django.db import migrations

DROP = """
DROP TABLE IF EXISTS wearables_dailymetric;
DROP TABLE IF EXISTS wearables_wearableconnection;
DELETE FROM django_migrations WHERE app = 'wearables';
"""


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.RunSQL(DROP, reverse_sql=migrations.RunSQL.noop),
    ]
