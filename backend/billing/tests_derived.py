"""Membership status, derived from the ledger rather than stored.

`MemberProfile.membership_status` is a cache of a fact the payments table
already holds, and every one of these tests works the same way: seed known
payments, work out independently what the answer has to be, and check the code
agrees. Asserting a 200 would pass just as happily with the number wrong.

The boundary is the part worth pinning. "Expired" means the period has ended,
and a member whose period ends today has not finished it -- they have paid for
today. Getting that off by one locks people out of the gym on the last day
they paid for, which is the kind of bug a member notices at the door.
"""

from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APITestCase

from core.testing import TenantAPIMixin

from accounts.models import MembershipStatus, MemberProfile, Role

from .models import PaymentStatus, Plan
from .services import compute_membership_status, record_payment, sync_membership_status

User = get_user_model()


def make_user(username, role=Role.MEMBER):
    user = User.objects.create_user(
        username=username, email=f"{username}@example.com", password="pass12345", role=role
    )
    MemberProfile.objects.get_or_create(user=user)
    return user


class ComputeMembershipStatusTests(TenantAPIMixin, APITestCase):
    """The derivation itself, at and around the boundary."""

    def setUp(self):
        self.member = make_user("derive_member")
        self.plan = Plan.objects.create(
            name="Monthly", price=Decimal("1000"), duration_days=30
        )
        self.today = timezone.localdate()

    def _pay_ending(self, days_from_today, status=PaymentStatus.COMPLETED):
        """A payment whose period ends exactly `days_from_today` from today."""
        paid_on = self.today + timedelta(days=days_from_today) - timedelta(days=30)
        payment = record_payment(
            member=self.member,
            plan=self.plan,
            amount=Decimal("1000"),
            method="cash",
            paid_date=paid_on,
            status=status,
        )
        # Independently confirm the fixture is what the name claims.
        self.assertEqual(payment.period_end, self.today + timedelta(days=days_from_today))
        return payment

    def test_a_period_ending_today_is_still_active(self):
        # The last day is paid for. Expiry is the day after it ends.
        self._pay_ending(0)
        self.assertEqual(compute_membership_status(self.member), MembershipStatus.ACTIVE)

    def test_a_period_that_ended_yesterday_is_expired(self):
        self._pay_ending(-1)
        self.assertEqual(compute_membership_status(self.member), MembershipStatus.EXPIRED)

    def test_a_period_ending_tomorrow_is_active(self):
        self._pay_ending(1)
        self.assertEqual(compute_membership_status(self.member), MembershipStatus.ACTIVE)

    def test_a_member_with_no_completed_payment_derives_nothing(self):
        # None, not "expired": a gym importing existing members should not have
        # every one of them flipped to expired the day this ships.
        self.assertIsNone(compute_membership_status(self.member))

    def test_a_pending_payment_does_not_count(self):
        self._pay_ending(30, status=PaymentStatus.PENDING)
        self.assertIsNone(compute_membership_status(self.member))

    def test_the_latest_period_wins_not_the_latest_payment(self):
        # Someone who renews early has two live payments; the one that reaches
        # furthest is the one that says whether they are a member today.
        self._pay_ending(-5)
        self._pay_ending(25)
        self.assertEqual(compute_membership_status(self.member), MembershipStatus.ACTIVE)


class SyncMembershipStatusTests(TenantAPIMixin, APITestCase):
    """Writing the derived status back, and when not to."""

    def setUp(self):
        self.member = make_user("sync_member")
        self.plan = Plan.objects.create(
            name="Monthly", price=Decimal("1000"), duration_days=30
        )
        self.today = timezone.localdate()

    def _pay_ending(self, days_from_today):
        return record_payment(
            member=self.member,
            plan=self.plan,
            amount=Decimal("1000"),
            method="cash",
            paid_date=self.today + timedelta(days=days_from_today) - timedelta(days=30),
        )

    def _status(self):
        self.member.profile.refresh_from_db()
        return self.member.profile.membership_status

    def _set_status(self, status):
        MemberProfile.objects.filter(user=self.member).update(membership_status=status)
        # Re-fetch: the update went round the instance, and `sync_membership_status`
        # reads `user.profile`, which is still holding the cached old row. Leaving
        # it stale makes the sync compare against the wrong "before" value and
        # decide it has nothing to write.
        self.member = User.objects.get(pk=self.member.pk)

    def test_a_lapsed_member_is_written_as_expired(self):
        self._pay_ending(-1)
        self._set_status(MembershipStatus.ACTIVE)
        sync_membership_status(self.member)
        self.assertEqual(self._status(), MembershipStatus.EXPIRED)

    def test_the_nightly_sweep_leaves_a_paused_member_alone(self):
        # Paused means an admin said "they told us they'd be away". A sweep
        # that overwrote it would silently cancel that decision every night.
        self._pay_ending(-1)
        self._set_status(MembershipStatus.PAUSED)
        sync_membership_status(self.member, respect_pause=True)
        self.assertEqual(self._status(), MembershipStatus.PAUSED)

    def test_a_new_payment_reactivates_even_a_paused_member(self):
        # The other direction, and the reason `respect_pause` is a parameter
        # rather than a rule: paying is an unambiguous "I'm back".
        self._set_status(MembershipStatus.PAUSED)
        self._pay_ending(30)
        sync_membership_status(self.member, respect_pause=False)
        self.assertEqual(self._status(), MembershipStatus.ACTIVE)

    def test_a_member_with_no_payment_is_left_untouched(self):
        self._set_status(MembershipStatus.ACTIVE)
        sync_membership_status(self.member)
        self.assertEqual(self._status(), MembershipStatus.ACTIVE)


class ExpireSubscriptionsCommandTests(TenantAPIMixin, APITestCase):
    """The nightly sweep, which runs unattended on a cron and had no tests."""

    def setUp(self):
        self.plan = Plan.objects.create(
            name="Monthly", price=Decimal("1000"), duration_days=30
        )
        self.today = timezone.localdate()

    def _member(self, username, ends_in_days, status=MembershipStatus.ACTIVE):
        member = make_user(username)
        record_payment(
            member=member,
            plan=self.plan,
            amount=Decimal("1000"),
            method="cash",
            paid_date=self.today + timedelta(days=ends_in_days) - timedelta(days=30),
        )
        MemberProfile.objects.filter(user=member).update(membership_status=status)
        return member

    def _status(self, member):
        return MemberProfile.objects.get(user=member).membership_status

    def _run(self):
        out = StringIO()
        call_command("expire_subscriptions", stdout=out)
        return out.getvalue()

    def test_a_lapsed_member_is_flipped(self):
        member = self._member("sweep_lapsed", ends_in_days=-1)
        self._run()
        self.assertEqual(self._status(member), MembershipStatus.EXPIRED)

    def test_a_member_whose_period_ends_today_is_left_active(self):
        member = self._member("sweep_today", ends_in_days=0)
        self._run()
        self.assertEqual(self._status(member), MembershipStatus.ACTIVE)

    def test_a_paused_member_is_not_swept(self):
        member = self._member("sweep_paused", ends_in_days=-5, status=MembershipStatus.PAUSED)
        self._run()
        self.assertEqual(self._status(member), MembershipStatus.PAUSED)

    def test_the_count_it_reports_matches_what_it_changed(self):
        lapsed = [self._member(f"sweep_l{n}", ends_in_days=-1) for n in range(3)]
        current = [self._member(f"sweep_c{n}", ends_in_days=10) for n in range(2)]

        output = self._run()

        # Worked out here rather than read off the command's own arithmetic.
        expected = sum(
            1 for m in lapsed + current if self._status(m) == MembershipStatus.EXPIRED
        )
        self.assertEqual(expected, 3)
        self.assertIn("3 expired", output)
        for member in current:
            self.assertEqual(self._status(member), MembershipStatus.ACTIVE)

    def test_running_it_twice_changes_nothing_the_second_time(self):
        # It is on a cron, so a retried run has to be harmless.
        member = self._member("sweep_twice", ends_in_days=-1)
        self._run()
        second = self._run()
        self.assertEqual(self._status(member), MembershipStatus.EXPIRED)
        self.assertIn("0 expired", second)


class MySubscriptionEndpointTests(TenantAPIMixin, APITestCase):
    """What the member's own screen reads, checked against the ledger."""

    def setUp(self):
        self.member = make_user("sub_member")
        self.plan = Plan.objects.create(
            name="Monthly", price=Decimal("1000"), duration_days=30
        )
        self.today = timezone.localdate()
        self.client.force_authenticate(self.member)

    def _pay(self, days_ago):
        return record_payment(
            member=self.member,
            plan=self.plan,
            amount=Decimal("1000"),
            method="cash",
            paid_date=self.today - timedelta(days=days_ago),
        )

    def test_days_remaining_matches_the_period_on_the_payment(self):
        payment = self._pay(days_ago=10)
        data = self.client.get("/api/billing/my-subscription/").data

        expected = (payment.period_end - self.today).days
        self.assertEqual(expected, 20)  # 30-day plan, 10 days in
        self.assertEqual(data["days_remaining"], expected)
        self.assertEqual(data["period_end"], payment.period_end)
        self.assertEqual(data["plan"]["name"], "Monthly")

    def test_days_remaining_is_zero_on_the_last_day_not_negative(self):
        self._pay(days_ago=30)
        data = self.client.get("/api/billing/my-subscription/").data
        self.assertEqual(data["days_remaining"], 0)

    def test_a_lapsed_membership_reports_zero_rather_than_a_negative(self):
        # Clamped: "-4 days remaining" is not something to put on a screen.
        self._pay(days_ago=45)
        data = self.client.get("/api/billing/my-subscription/").data
        self.assertEqual(data["days_remaining"], 0)

    def test_a_member_who_has_never_paid_gets_nulls_not_an_error(self):
        data = self.client.get("/api/billing/my-subscription/").data
        self.assertIsNone(data["plan"])
        self.assertIsNone(data["period_end"])
        self.assertIsNone(data["days_remaining"])
