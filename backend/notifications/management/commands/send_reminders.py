from django.core.management.base import BaseCommand
from django.utils import timezone

from notifications.services import (
    expiring_members,
    just_expired_members,
    sweep_all_tenants,
)


class Command(BaseCommand):
    help = (
        "Emails members whose membership is about to end, and those whose "
        "period ran out yesterday. Safe to run more than once a day: a message "
        "is keyed on what it is about, so the second run sends nothing. "
        "Intended for a daily schedule (e.g. a Render Cron Job) alongside "
        "expire_subscriptions -- not wired up automatically."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List who would be written to without sending anything.",
        )

    def handle(self, *args, **options):
        today = timezone.localdate()

        if options["dry_run"]:
            rows = 0
            for member, payment, days_left in expiring_members(today):
                self.stdout.write(
                    f"  expiring  {member.username:<20} {payment.period_end} "
                    f"({days_left}d) -> {member.email or 'no email on file'}"
                )
                rows += 1
            for member, payment in just_expired_members(today):
                self.stdout.write(
                    f"  expired   {member.username:<20} {payment.period_end} "
                    f"-> {member.email or 'no email on file'}"
                )
                rows += 1
            self.stdout.write(self.style.SUCCESS(f"{rows} member(s) would be emailed."))
            return

        # Every gym on the platform, each inside its own scope.
        sent, skipped = sweep_all_tenants(today)
        self.stdout.write(
            self.style.SUCCESS(
                f"Sent {sent} reminder(s); {skipped} already sent or had no email on file."
            )
        )
