"""The scheduled jobs, run the way cron runs them: with no gym in scope.

Every other suite reaches the application through `TenantAPIMixin`, which puts a
gym in scope before the test body runs. Cron does not: a management command
starts with nothing resolved, which is why these commands have to sweep gym by
gym. These tests deliberately do not use that mixin -- they create two gyms,
leave the scope empty, and call the commands exactly as the scheduler does.
"""

import io
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from accounts.models import MemberProfile, MembershipStatus, Role
from billing.models import Plan
from billing.services import record_payment
from core.testing import enrol, founding_tenant
from tenancy import context
from tenancy.sweeps import for_each_tenant

User = get_user_model()


class NoScopeTestCase(TestCase):
    """Two gyms, and nothing in scope when the test body starts."""

    def setUp(self):
        self.today = timezone.localdate()
        _, self.gym_a = founding_tenant("alpha")
        _, self.gym_b = founding_tenant("beta")
        self.plans = {}
        for gym in (self.gym_a, self.gym_b):
            with context.scope(gym):
                self.plans[gym.pk] = Plan.objects.create(
                    name="Monthly", price=Decimal("1000"), duration_days=30
                )
        self.assertIsNone(context.get(), "the scope must be empty, as it is on cron")

    def member(self, gym, username, ends_in_days, status=MembershipStatus.ACTIVE):
        """A member of `gym` whose paid period ends `ends_in_days` from today."""
        with context.scope(gym):
            user = User.objects.create_user(
                username=username, email=f"{username}@example.com",
                password="pass12345", role=Role.MEMBER,
            )
            MemberProfile.objects.get_or_create(user=user)
            enrol(user)
            record_payment(
                member=user,
                plan=self.plans[gym.pk],
                amount=Decimal("1000"),
                method="cash",
                paid_date=self.today + timedelta(days=ends_in_days) - timedelta(days=30),
            )
            MemberProfile.objects.filter(user=user).update(membership_status=status)
        return user

    def status_of(self, user):
        return MemberProfile.objects.get(user=user).membership_status


class ExpireSubscriptionsFromCronTests(NoScopeTestCase):
    def test_it_runs_with_no_tenant_in_scope(self):
        """A. The crash this fixes: the command used to raise TenantScopeError."""
        lapsed = self.member(self.gym_a, "cron_lapsed", ends_in_days=-1)

        call_command("expire_subscriptions", stdout=io.StringIO())

        self.assertEqual(self.status_of(lapsed), MembershipStatus.EXPIRED)

    def test_every_gym_is_swept(self):
        """D. Both gyms, not just whichever happened to be resolved."""
        lapsed_a = self.member(self.gym_a, "cron_a", ends_in_days=-2)
        lapsed_b = self.member(self.gym_b, "cron_b", ends_in_days=-2)
        current_b = self.member(self.gym_b, "cron_b_current", ends_in_days=10)

        out = io.StringIO()
        call_command("expire_subscriptions", stdout=out)

        self.assertEqual(self.status_of(lapsed_a), MembershipStatus.EXPIRED)
        self.assertEqual(self.status_of(lapsed_b), MembershipStatus.EXPIRED)
        self.assertEqual(self.status_of(current_b), MembershipStatus.ACTIVE)
        printed = out.getvalue()
        self.assertIn(self.gym_a.slug, printed)
        self.assertIn(self.gym_b.slug, printed)

    def test_a_paused_member_is_still_left_alone(self):
        """The sweep's existing semantics survive the move to per-gym scopes."""
        paused = self.member(
            self.gym_a, "cron_paused", ends_in_days=-5, status=MembershipStatus.PAUSED
        )

        call_command("expire_subscriptions", stdout=io.StringIO())

        self.assertEqual(self.status_of(paused), MembershipStatus.PAUSED)

    def test_the_scope_is_empty_again_afterwards(self):
        """F. The sweep leaves nothing set for whatever runs next."""
        self.member(self.gym_a, "cron_after", ends_in_days=-1)

        call_command("expire_subscriptions", stdout=io.StringIO())

        self.assertIsNone(context.get())

    def test_an_outer_scope_is_restored(self):
        """F. Called from inside a scope, it hands that scope back unchanged."""
        with context.scope(self.gym_b):
            call_command("expire_subscriptions", stdout=io.StringIO())
            self.assertEqual(context.get(), self.gym_b)


class SendRemindersFromCronTests(NoScopeTestCase):
    def test_dry_run_works_with_no_tenant_in_scope(self):
        """B. The dry run used to raise TenantScopeError before printing anything."""
        self.member(self.gym_a, "dry_soon", ends_in_days=3)

        out = io.StringIO()
        call_command("send_reminders", "--dry-run", stdout=out)

        printed = out.getvalue()
        self.assertIn("dry_soon", printed)
        self.assertIn("1 member(s) would be emailed.", printed)
        self.assertIsNone(context.get())

    def test_the_dry_run_covers_every_gym(self):
        """D. One line per gym's members, not only the first gym's."""
        self.member(self.gym_a, "dry_a", ends_in_days=7)
        self.member(self.gym_b, "dry_b", ends_in_days=7)

        out = io.StringIO()
        call_command("send_reminders", "--dry-run", stdout=out)

        self.assertIn("dry_a", out.getvalue())
        self.assertIn("dry_b", out.getvalue())

    def test_the_send_path_still_sweeps_every_gym(self):
        from django.core import mail

        self.member(self.gym_a, "send_a", ends_in_days=7)
        self.member(self.gym_b, "send_b", ends_in_days=7)

        call_command("send_reminders", stdout=io.StringIO())

        self.assertEqual(len(mail.outbox), 2)
        self.assertIsNone(context.get())


class WhatsAppRemindersFromCronTests(NoScopeTestCase):
    """C. The WhatsApp sweep had no per-gym loop at all and raised immediately."""

    def test_the_sweep_runs_with_no_tenant_in_scope(self):
        from messaging.services import sweep_all_tenants

        self.member(self.gym_a, "wa_soon", ends_in_days=3)

        sent, skipped, failures = sweep_all_tenants(self.today)

        # No phone number on file, so nothing is sent -- the point is that
        # reading who is due no longer raises for want of a tenant.
        self.assertEqual((sent, failures), (0, []))
        self.assertEqual(skipped, 1)
        self.assertIsNone(context.get())

    @mock.patch("messaging.whatsapp.is_configured", return_value=True)
    @mock.patch("messaging.services.send")
    def test_the_command_sweeps_every_gym(self, send, _is_configured):
        for gym, username in ((self.gym_a, "wa_a"), (self.gym_b, "wa_b")):
            member = self.member(gym, username, ends_in_days=1)
            MemberProfile.objects.filter(user=member).update(phone="+91 90000 00001")

        call_command("send_whatsapp_reminders", stdout=io.StringIO())

        self.assertEqual(send.call_count, 2)
        self.assertIsNone(context.get())


class OneGymFailingTests(NoScopeTestCase):
    """E. A gym that raises must not take the others' work with it."""

    def test_the_other_gym_is_still_swept_and_its_scope_is_its_own(self):
        seen = []

        def job(tenant):
            seen.append((tenant.slug, context.get().slug))
            if tenant == self.gym_a:
                raise RuntimeError("this gym is broken")
            return "done"

        # Named explicitly: a migrated database already has its founding gym,
        # and this test is about what happens either side of the failure.
        results, failures = for_each_tenant(job, tenants=[self.gym_a, self.gym_b])

        # Gym A raised; gym B still ran, and ran in its own scope.
        self.assertEqual([(t.slug, value) for t, value in results], [(self.gym_b.slug, "done")])
        self.assertEqual([t.slug for t, _ in failures], [self.gym_a.slug])
        self.assertEqual(seen, [(self.gym_a.slug, self.gym_a.slug),
                                (self.gym_b.slug, self.gym_b.slug)])
        self.assertIsNone(context.get())

    def test_the_command_reports_a_failing_gym_rather_than_looking_clean(self):
        self.member(self.gym_b, "fail_b", ends_in_days=-1)
        real = MembershipStatus.ACTIVE

        def explode(user, **kwargs):
            if user.username == "fail_a":
                raise RuntimeError("ledger unavailable")
            user.profile.membership_status = MembershipStatus.EXPIRED
            user.profile.save(update_fields=["membership_status"])

        self.member(self.gym_a, "fail_a", ends_in_days=-1, status=real)
        with mock.patch(
            "billing.management.commands.expire_subscriptions.sync_membership_status",
            side_effect=explode,
        ):
            with self.assertRaises(CommandError) as raised:
                call_command("expire_subscriptions", stdout=io.StringIO())

        self.assertIn(self.gym_a.slug, str(raised.exception))
        # The healthy gym was still swept before the failure was reported.
        self.assertEqual(self.status_of(User.objects.get(username="fail_b")),
                         MembershipStatus.EXPIRED)
        self.assertIsNone(context.get())
