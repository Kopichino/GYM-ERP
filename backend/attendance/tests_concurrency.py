"""One open check-in per user, under genuine concurrency.

`attendance/tests.py` already proves a second sequential check-in is refused.
That is the easy half. The rule that matters is the one the docstring in
`services.py` claims: that the partial unique index, not the `exists()` check
above it, is what stops a double-tapped turnstile from opening two visits. The
only way to show that is to have both taps arrive at once.

TransactionTestCase rather than TestCase: threads get their own connections,
and a rolled-back outer transaction is invisible to them.
"""

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase

from accounts.models import MemberProfile, Role
from billing.models import DayPass
from core.testing import losers, requires_row_locks, run_concurrently, winners

from .models import CheckInMethod, CheckInOut
from .services import AttendanceError, open_visit, toggle_guest_visit, toggle_visit

User = get_user_model()


def make_user(username, role=Role.MEMBER):
    user = User.objects.create_user(
        username=username, email=f"{username}@example.com", password="pass12345", role=role
    )
    if role == Role.MEMBER:
        MemberProfile.objects.get_or_create(user=user)
    return user


class _ScopedTransactionTestCase(TransactionTestCase):
    """A tenant in scope for the whole test.

    These drive services directly rather than through the API, so nothing has
    resolved a tenant for them -- and the scoped managers refuse to run without
    one. Threads do NOT inherit a ContextVar context, so `run_concurrently`
    copies it across explicitly; see core.testing.

    `setUp`, not `_pre_setup`: on TransactionTestCase that hook is a
    *classmethod*, so overriding it as an instance method breaks its contract
    and every class errors before a test runs. The subclasses below therefore
    have to call super().setUp() -- without it the scope never opens and every
    worker thread raises.
    """

    def setUp(self):
        super().setUp()
        from core.testing import founding_tenant
        from tenancy import context

        _, self.tenant = founding_tenant("racegym")
        self._tenancy_token = context.set(self.tenant)

    def tearDown(self):
        from tenancy import context

        token = getattr(self, "_tenancy_token", None)
        if token is not None:
            context.reset(token)
            self._tenancy_token = None
        super().tearDown()


@requires_row_locks
class ConcurrentCheckInTests(_ScopedTransactionTestCase):
    # No reset_sequences: the tenancy fixtures insert an Organisation, and
    # resetting the sequence hands that id out a second time. Nothing here
    # depends on primary key values.

    def setUp(self):
        super().setUp()
        self.member = make_user("conc_member")

    def _open_visits(self):
        return CheckInOut.objects.filter(user=self.member, check_out_time__isnull=True)

    def test_two_simultaneous_taps_open_one_visit(self):
        results = run_concurrently(lambda _: open_visit(self.member), count=2)

        self.assertEqual(len(winners(results)), 1)
        self.assertEqual(self._open_visits().count(), 1)

    def test_the_loser_is_told_they_are_already_in(self):
        results = run_concurrently(lambda _: open_visit(self.member), count=2)

        refused = losers(results)
        self.assertEqual(len(refused), 1)
        # A readable refusal, not an IntegrityError leaking out of the service.
        self.assertIsInstance(refused[0], AttendanceError)
        self.assertIn("Already checked in", str(refused[0]))

    def test_a_crowd_of_taps_still_opens_one_visit(self):
        # Eight terminals, one member, one visit. The index is the arbiter.
        results = run_concurrently(lambda _: open_visit(self.member), count=8)

        self.assertEqual(len(winners(results)), 1)
        self.assertEqual(len(losers(results)), 7)
        self.assertEqual(self._open_visits().count(), 1)
        self.assertTrue(all(isinstance(e, AttendanceError) for e in losers(results)))

    def test_two_members_do_not_block_each_other(self):
        # The rule is per user; two different people arriving together must
        # both get in, or a busy 6pm would start refusing legitimate check-ins.
        other = make_user("conc_other")
        people = [self.member, other]
        results = run_concurrently(lambda i: open_visit(people[i]), count=2)

        self.assertEqual(len(winners(results)), 2)
        self.assertEqual(CheckInOut.objects.filter(check_out_time__isnull=True).count(), 2)

    def test_a_closed_visit_leaves_the_slot_free(self):
        # The index only counts open visits, so yesterday's closed row must not
        # stop today's check-in even when two taps race for it.
        first = open_visit(self.member)
        first.check_out_time = first.check_in_time
        first.save(update_fields=["check_out_time"])

        results = run_concurrently(lambda _: open_visit(self.member), count=4)
        self.assertEqual(len(winners(results)), 1)
        self.assertEqual(self._open_visits().count(), 1)

    def test_racing_toggles_never_leave_two_visits_open(self):
        # What a turnstile actually does. Whichever way the toggles interleave,
        # the invariant is the same: never two open rows for one member.
        run_concurrently(lambda _: toggle_visit(self.member, method=CheckInMethod.BIOMETRIC), count=6)
        self.assertLessEqual(self._open_visits().count(), 1)


@requires_row_locks
@requires_row_locks
class ConcurrentGuestCheckInTests(_ScopedTransactionTestCase):
    # No reset_sequences: the tenancy fixtures insert an Organisation, and
    # resetting the sequence hands that id out a second time. Nothing here
    # depends on primary key values.

    def setUp(self):
        super().setUp()
        self.admin = make_user("conc_gate_admin", role=Role.ADMIN)
        self.day_pass = DayPass.objects.create(
            name="Walk-in", amount=0, issued_by=self.admin
        )

    def _open_guest_visits(self):
        return CheckInOut.objects.filter(
            day_pass=self.day_pass, check_out_time__isnull=True
        ).count()

    def test_racing_taps_never_open_two_guest_visits(self):
        """A day pass has its own index for the same reason a member does: a
        guest row is a real visit and two open ones double-count the guest in
        every occupancy figure.

        The assertion is "never more than one", not "exactly one". This is a
        toggle, so one legitimate interleaving is open-then-close, which ends
        at zero -- pinning it to exactly one would fail on a correct run. The
        race is repeated because that interleaving is the common one, and a
        single attempt would mostly not exercise the index at all.
        """
        for _ in range(10):
            CheckInOut.objects.filter(day_pass=self.day_pass).delete()
            run_concurrently(lambda _: toggle_guest_visit(self.day_pass), count=2)
            self.assertLessEqual(
                self._open_guest_visits(), 1, "two guest visits were open at once"
            )

    def test_a_tap_pair_never_writes_two_open_rows(self):
        # The stronger half, stated in rows rather than counts: whatever the
        # interleaving, the pass never holds two live visits.
        run_concurrently(lambda _: toggle_guest_visit(self.day_pass), count=6)
        self.assertLessEqual(self._open_guest_visits(), 1)

    def test_a_guest_race_does_not_touch_member_visits(self):
        member = make_user("conc_gate_member")
        open_visit(member)
        run_concurrently(lambda _: toggle_guest_visit(self.day_pass), count=4)

        self.assertEqual(
            CheckInOut.objects.filter(user=member, check_out_time__isnull=True).count(), 1
        )
