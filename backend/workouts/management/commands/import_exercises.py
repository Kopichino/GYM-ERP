from pathlib import Path

import openpyxl
from django.core.management.base import BaseCommand

from workouts.models import Exercise, ExerciseVideo

DATASET_PATH = Path(__file__).resolve().parent.parent.parent / "fixtures" / "exercise_dataset.xlsx"


class Command(BaseCommand):
    help = (
        "Import the muscle/region/exercise/video catalog from the bundled xlsx "
        "dataset into Exercise and ExerciseVideo. Safe to re-run -- rows are "
        "upserted by exercise name."
    )

    def handle(self, *args, **options):
        workbook = openpyxl.load_workbook(DATASET_PATH, read_only=True, data_only=True)
        sheet = workbook.active

        created = updated = videos_added = 0
        for muscle, region, name, video_url in sheet.iter_rows(min_row=2, values_only=True):
            if not name:
                continue
            name = name.strip()
            exercise, was_created = Exercise.objects.update_or_create(
                name=name,
                defaults={
                    "muscle_group": (muscle or "").strip(),
                    "region": (region or "").strip(),
                },
            )
            created += was_created
            updated += not was_created

            if video_url:
                _, video_created = ExerciseVideo.objects.get_or_create(
                    exercise=exercise, url=video_url.strip(), defaults={"title": name}
                )
                videos_added += video_created

        self.stdout.write(
            self.style.SUCCESS(
                f"Exercises: {created} created, {updated} updated. Videos: {videos_added} added."
            )
        )
