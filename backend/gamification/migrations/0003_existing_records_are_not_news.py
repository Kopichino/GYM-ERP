"""Stamp every record that existed before the celebration feature as seen.

Without this, `seen_at` arrives NULL on the whole back catalogue and the first
member to open the app after deploying is congratulated on every PR they have
ever set. A record from two years ago is not news, and the point of the feature
is the moment -- not a list.

Irreversible on purpose: going back would mean guessing which of these the
member had actually been shown, and the honest answer is all of them.
"""

from django.db import migrations
from django.utils import timezone


def mark_history_seen(apps, schema_editor):
    PersonalRecord = apps.get_model("gamification", "PersonalRecord")
    PersonalRecord.objects.filter(seen_at__isnull=True).update(seen_at=timezone.now())


class Migration(migrations.Migration):

    dependencies = [
        ("gamification", "0002_remove_badge_one_badge_per_criterion_threshold_and_more"),
    ]

    operations = [
        migrations.RunPython(mark_history_seen, migrations.RunPython.noop),
    ]
