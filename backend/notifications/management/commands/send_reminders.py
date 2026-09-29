from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from notifications.services import (
    expiring_members,
    just_expired_members,
    sweep_all_tenants,
)
from tenancy.sweeps import for_each_tenant


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
            # Gym by gym, like the real sweep: cron has no tenant in scope, and
            # the ledger these read is scoped to one gym.
            results, failures = for_each_tenant(lambda tenant: self._listing(tenant, today))
            rows = sum(gym_rows for _, gym_rows in results)
            self.stdout.write(self.style.SUCCESS(f"{rows} member(s) would be emailed."))
            self._report(failures)
            return

        # Every gym on the platform, each inside its own scope.
        sent, skipped, failures = sweep_all_tenants(today)
        self.stdout.write(
            self.style.SUCCESS(
                f"Sent {sent} reminder(s); {skipped} already sent or had no email on file."
            )
        )
        self._report(failures)

    def _listing(self, tenant, today):
        """Runs inside `tenant`'s scope. Returns how many rows it printed."""
        rows = 0
        for member, payment, days_left in expiring_members(today):
            self.stdout.write(
                f"  {tenant.slug}  expiring  {member.username:<20} {payment.period_end} "
                f"({days_left}d) -> {member.email or 'no email on file'}"
            )
            rows += 1
        for member, payment in just_expired_members(today):
            self.stdout.write(
                f"  {tenant.slug}  expired   {member.username:<20} {payment.period_end} "
                f"-> {member.email or 'no email on file'}"
            )
            rows += 1
        return rows

    def _report(self, failures):
        if failures:
            raise CommandError(
                "Failed for: "
                + ", ".join(f"{tenant.slug} ({error})" for tenant, error in failures)
            )
