from django.core.management.base import BaseCommand
from django.utils import timezone

from messaging.services import send_expiry_reminders
from messaging.whatsapp import is_configured


class Command(BaseCommand):
    help = (
        "WhatsApps members whose membership is about to end. Shares the "
        "notification log with the email sweep, so a member is nudged on one "
        "channel per day, not both. Run this instead of send_reminders, not "
        "alongside it, unless you want email to be the fallback."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--template",
            default="membership_expiring",
            help="The approved WhatsApp template name to send.",
        )

    def handle(self, *args, **options):
        if not is_configured():
            self.stdout.write(
                self.style.WARNING(
                    "WhatsApp isn't configured (WHATSAPP_TOKEN / "
                    "WHATSAPP_PHONE_NUMBER_ID). Nothing sent."
                )
            )
            return
        sent, skipped = send_expiry_reminders(
            timezone.localdate(), template=options["template"]
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Sent {sent} WhatsApp reminder(s); {skipped} skipped "
                "(already nudged today, or no number on file)."
            )
        )
