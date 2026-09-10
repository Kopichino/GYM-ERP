from django.core.management.base import BaseCommand

from accounts.models import MembershipStatus, Role, User
from billing.services import sync_membership_status


class Command(BaseCommand):
    help = (
        "Sweeps members whose subscription period has lapsed with no new "
        "payment and flips their membership_status to expired. Skips members "
        "an admin has manually paused. Intended to run on a daily schedule "
        "(e.g. a Render Cron Job) -- not wired up automatically."
    )

    def handle(self, *args, **options):
        members = User.objects.filter(
            role=Role.MEMBER, profile__membership_status=MembershipStatus.ACTIVE
        )
        flipped = 0
        for member in members:
            before = member.profile.membership_status
            sync_membership_status(member, respect_pause=True)
            member.profile.refresh_from_db()
            if member.profile.membership_status != before:
                flipped += 1
        self.stdout.write(self.style.SUCCESS(f"Checked {members.count()} active members, {flipped} expired."))
