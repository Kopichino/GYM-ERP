from django.core.management.base import BaseCommand, CommandError

from accounts.models import MembershipStatus
from billing.services import sync_membership_status
from tenancy.people import members_here
from tenancy.sweeps import for_each_tenant


class Command(BaseCommand):
    help = (
        "Sweeps members whose subscription period has lapsed with no new "
        "payment and flips their membership_status to expired. Skips members "
        "an admin has manually paused. Runs once per gym, each inside its own "
        "tenant scope, because a member's standing is read from that gym's "
        "ledger. Intended for a daily schedule (see backend/nightly.sh)."
    )

    def handle(self, *args, **options):
        results, failures = for_each_tenant(self._sweep_one_gym)

        checked = sum(gym_checked for _, (gym_checked, _) in results)
        flipped = sum(gym_flipped for _, (_, gym_flipped) in results)
        for tenant, (gym_checked, gym_flipped) in results:
            self.stdout.write(f"  {tenant.slug}: checked {gym_checked}, expired {gym_flipped}")
        self.stdout.write(
            self.style.SUCCESS(
                f"Checked {checked} active member(s) across {len(results)} gym(s), "
                f"{flipped} expired."
            )
        )
        if failures:
            # Loud, so a scheduler that only watches exit codes still notices --
            # after the gyms that did work have been reported.
            raise CommandError(
                "Failed for: "
                + ", ".join(f"{tenant.slug} ({error})" for tenant, error in failures)
            )

    def _sweep_one_gym(self, tenant):
        """Runs inside `tenant`'s scope, so every read is that gym's own."""
        members = members_here().filter(
            profile__membership_status=MembershipStatus.ACTIVE
        ).select_related("profile")

        checked = flipped = 0
        for member in members:
            before = member.profile.membership_status
            sync_membership_status(member, respect_pause=True)
            member.profile.refresh_from_db()
            checked += 1
            flipped += member.profile.membership_status != before
        return checked, flipped
