from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from accounts.models import MemberProfile, MembershipStatus, Role
from billing.models import PaymentMethod, Plan
from billing.services import record_payment

from .models import NotificationKind, NotificationLog
from .services import EXPIRY_WINDOWS, expiring_members, send_expiry_reminders

from core.testing import TenantAPIMixin, enrol

User = get_user_model()
TODAY = timezone.localdate()


def make_member(username, email=None):
    user = User.objects.create_user(
        username=username,
        email=email if email is not None else f"{username}@example.com",
        password="pass12345",
        role=Role.MEMBER,
    )
    MemberProfile.objects.get_or_create(user=user)
    enrol(user)
    return user


class ExpiryReminderTests(TenantAPIMixin, TestCase):
    """Who gets written to is read off the ledger; what has been sent is the
    only thing stored."""

    def setUp(self):
        self.plan = Plan.objects.create(
            name="Monthly", price=Decimal("1500"), duration_days=30
        )

    def pay_expiring_in(self, member, days):
        """Backdates a payment so its period ends `days` from today."""
        paid_on = TODAY + timedelta(days=days) - timedelta(days=self.plan.duration_days)
        return record_payment(
            member=member,
            plan=self.plan,
            amount=self.plan.price,
            method=PaymentMethod.CASH,
            paid_date=paid_on,
        )

    def test_a_member_inside_a_window_is_emailed_once(self):
        member = make_member("soon")
        self.pay_expiring_in(member, 3)

        sent, _ = send_expiry_reminders()
        self.assertEqual(sent, 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("3 days", mail.outbox[0].subject)
        self.assertEqual(mail.outbox[0].to, ["soon@example.com"])

    def test_running_the_sweep_twice_sends_nothing_the_second_time(self):
        member = make_member("twice")
        self.pay_expiring_in(member, 7)

        send_expiry_reminders()
        mail.outbox.clear()
        sent, skipped = send_expiry_reminders()

        self.assertEqual(sent, 0)
        self.assertEqual(skipped, 1)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(NotificationLog.objects.count(), 1)

    def test_each_window_is_its_own_message(self):
        """Seven days out and one day out are different nudges, not a repeat."""
        member = make_member("nudged")
        payment = self.pay_expiring_in(member, 7)
        send_expiry_reminders()

        # Six days pass; the same expiry is now one day away.
        later = TODAY + timedelta(days=6)
        sent, _ = send_expiry_reminders(on=later)
        self.assertEqual(sent, 1)
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn("tomorrow", mail.outbox[1].subject)
        # Two rows, keyed on the day each nudge fired rather than the expiry.
        self.assertEqual(NotificationLog.objects.count(), 2)
        self.assertEqual(
            sorted(NotificationLog.objects.values_list("subject_date", flat=True)),
            sorted([TODAY, later]),
        )
        self.assertEqual(payment.period_end, TODAY + timedelta(days=7))

    def test_renewing_takes_a_member_off_the_list(self):
        member = make_member("renewer")
        self.pay_expiring_in(member, 3)
        # They renew before the sweep runs; the new period ends 30 days out.
        record_payment(
            member=member,
            plan=self.plan,
            amount=self.plan.price,
            method=PaymentMethod.CASH,
        )
        self.assertEqual(list(expiring_members()), [])
        self.assertEqual(send_expiry_reminders()[0], 0)

    def test_a_paused_member_is_left_alone(self):
        member = make_member("paused")
        self.pay_expiring_in(member, 1)
        MemberProfile.objects.filter(user=member).update(
            membership_status=MembershipStatus.PAUSED
        )
        self.assertEqual(send_expiry_reminders()[0], 0)

    def test_a_member_with_no_email_is_skipped_not_crashed_on(self):
        member = make_member("noemail", email="")
        self.pay_expiring_in(member, 1)
        sent, skipped = send_expiry_reminders()
        self.assertEqual((sent, skipped), (0, 1))
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(NotificationLog.objects.exists())

    def test_a_member_outside_every_window_hears_nothing(self):
        member = make_member("quiet")
        self.pay_expiring_in(member, 5)  # 5 is not one of 7 / 3 / 1
        self.assertEqual(send_expiry_reminders()[0], 0)

    def test_windows_are_the_ones_advertised(self):
        self.assertEqual(EXPIRY_WINDOWS, (7, 3, 1))

    def test_a_member_who_never_paid_is_not_chased(self):
        make_member("neverpaid")
        self.assertEqual(send_expiry_reminders()[0], 0)


class ExpiredNoticeTests(TenantAPIMixin, TestCase):
    def setUp(self):
        self.plan = Plan.objects.create(
            name="Monthly", price=Decimal("1500"), duration_days=30
        )
        self.member = make_member("lapsed")
        # Period ended yesterday.
        record_payment(
            member=self.member,
            plan=self.plan,
            amount=self.plan.price,
            method=PaymentMethod.CASH,
            paid_date=TODAY - timedelta(days=31),
        )

    def test_the_day_after_expiry_they_get_one_notice(self):
        sent, _ = send_expiry_reminders()
        self.assertEqual(sent, 1)
        self.assertIn("expired", mail.outbox[0].subject)
        self.assertEqual(
            NotificationLog.objects.get().kind, NotificationKind.EXPIRED
        )

    def test_the_notice_is_not_repeated_the_following_day(self):
        send_expiry_reminders()
        mail.outbox.clear()
        self.assertEqual(send_expiry_reminders(on=TODAY + timedelta(days=1))[0], 0)
        self.assertEqual(len(mail.outbox), 0)


class SendRemindersCommandTests(TenantAPIMixin, TestCase):
    def setUp(self):
        self.plan = Plan.objects.create(
            name="Monthly", price=Decimal("1500"), duration_days=30
        )
        self.member = make_member("cronned")
        record_payment(
            member=self.member,
            plan=self.plan,
            amount=self.plan.price,
            method=PaymentMethod.CASH,
            paid_date=TODAY - timedelta(days=29),  # ends tomorrow
        )

    def test_dry_run_sends_nothing(self):
        call_command("send_reminders", "--dry-run")
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(NotificationLog.objects.exists())

    def test_the_command_sends(self):
        call_command("send_reminders")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(NotificationLog.objects.count(), 1)
