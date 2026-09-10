"""One live PT booking per slot, under genuine concurrency.

This invariant is held two different ways, and both need testing:

* the partial unique index on (trainer, date, start_time) catches an exact
  clash -- a double-tapped Book button, two members on the same slot;
* the `select_for_update()` on the trainer's day is *meant* to catch a partial
  overlap, which no index can express. 09:00-10:00 and 09:30-10:30 have
  different start times, so the index lets both through.

These tests found that the second did not hold. `SELECT ... FOR UPDATE` locks
the rows it matches, and on a trainer's first booking of the day it matched
none -- so nothing was held and both writers proceeded. The same hole showed
from the member's side, two trainers being booked for one member at the same
hour locking different (empty) session sets.

`book_session` now locks the trainer and member rows instead, which exist
whether or not anything is booked yet. Two bookings can only clash if they
share a person, so those two rows are exactly the common ground they need.

Either way this file needs Postgres: on SQLite the lock is a no-op outright.
"""

from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from django.utils import timezone

from accounts.models import MemberProfile, Role
from core.testing import losers, requires_row_locks, run_concurrently, winners

from .models import Availability, PTSession, SessionStatus
from .services import BookingError, book_session, cancel_session

User = get_user_model()

# Enough repetitions that an intermittent race shows up every run.
ATTEMPTS = 15


def make_user(username, role=Role.MEMBER):
    user = User.objects.create_user(
        username=username, email=f"{username}@example.com", password="pass12345", role=role
    )
    if role == Role.MEMBER:
        MemberProfile.objects.get_or_create(user=user)
    return user


def next_weekday(weekday):
    day = timezone.localdate() + timedelta(days=1)
    while day.weekday() != weekday:
        day += timedelta(days=1)
    return day


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
class ConcurrentBookingTests(_ScopedTransactionTestCase):
    # No reset_sequences: the tenancy fixtures insert an Organisation, and
    # resetting the sequence hands that id out a second time. Nothing here
    # depends on primary key values.

    def setUp(self):
        super().setUp()
        self.trainer = make_user("conc_coach", Role.TRAINER)
        self.day = next_weekday(2)
        Availability.objects.create(
            trainer=self.trainer, weekday=2, start_time=time(9), end_time=time(17)
        )

    def _book(self, member, start, end):
        return book_session(
            trainer=self.trainer,
            member=member,
            on=self.day,
            start_time=start,
            end_time=end,
        )

    def _live(self):
        return PTSession.objects.filter(
            trainer=self.trainer, date=self.day, status=SessionStatus.BOOKED
        )

    def _race_repeatedly(self, action, attempts=None):
        """Run a two-caller race `attempts` times; count the double-bookings.

        A race that only sometimes slips through makes for a test that only
        sometimes fails, which is worse than no test -- it would flap in CI and
        get muted. Repeating the race turns an intermittent bug into a reliable
        signal, and a correct implementation stays at zero however many times
        it is asked.
        """
        doubled = 0
        for attempt in range(attempts or ATTEMPTS):
            PTSession.objects.all().delete()
            results = run_concurrently(lambda i: action(attempt, i), count=2)
            if len(winners(results)) > 1:
                doubled += 1
        return doubled

    def test_two_members_racing_for_one_slot_yields_one_booking(self):
        members = [make_user("conc_a"), make_user("conc_b")]
        results = run_concurrently(
            lambda i: self._book(members[i], time(9), time(10)), count=2
        )

        self.assertEqual(len(winners(results)), 1)
        self.assertEqual(self._live().count(), 1)

    def test_the_loser_gets_a_readable_refusal(self):
        members = [make_user("conc_c"), make_user("conc_d")]
        results = run_concurrently(
            lambda i: self._book(members[i], time(9), time(10)), count=2
        )

        refused = losers(results)
        self.assertEqual(len(refused), 1)
        self.assertIsInstance(refused[0], BookingError)
        self.assertIn("just been taken", str(refused[0]))

    def test_a_double_tapped_book_button_books_once(self):
        member = make_user("conc_double")
        results = run_concurrently(lambda _: self._book(member, time(9), time(10)), count=5)

        self.assertEqual(len(winners(results)), 1)
        self.assertEqual(self._live().count(), 1)

    def test_a_partial_overlap_is_refused_too(self):
        """The case the unique index cannot see.

        09:00-10:00 and 09:30-10:30 have different start times, so the index
        lets both through by design and the lock is the only thing standing
        between the trainer and being sold to two people at 09:45.

        This test is why `book_session` locks the trainer and member rows
        rather than the trainer's existing sessions: the old lock matched no
        rows on an empty day, held nothing, and let both bookings through.
        """
        windows = [(time(9), time(10)), (time(9, 30), time(10, 30))]
        # Created up front for the same reason as below: the race has to be
        # about the booking, not about creating two users at once.
        pairs = [
            [make_user(f"ov_{n}_0"), make_user(f"ov_{n}_1")] for n in range(ATTEMPTS)
        ]
        doubled = self._race_repeatedly(
            lambda attempt, i: self._book(pairs[attempt][i], *windows[i])
        )
        self.assertEqual(doubled, 0, f"{doubled}/{ATTEMPTS} races double-booked the trainer")

    def test_different_slots_do_not_block_each_other(self):
        # A trainer with a full day must still be bookable in parallel, or the
        # lock would turn a busy schedule into a queue.
        members = [make_user("conc_g"), make_user("conc_h"), make_user("conc_i")]
        starts = [time(9), time(11), time(14)]
        results = run_concurrently(
            lambda i: self._book(members[i], starts[i], time(starts[i].hour + 1)), count=3
        )

        self.assertEqual(len(winners(results)), 3)
        self.assertEqual(self._live().count(), 3)

    def test_two_trainers_do_not_block_each_other(self):
        other = make_user("conc_coach2", Role.TRAINER)
        Availability.objects.create(
            trainer=other, weekday=2, start_time=time(9), end_time=time(17)
        )
        coaches = [self.trainer, other]
        members = [make_user("conc_j"), make_user("conc_k")]

        results = run_concurrently(
            lambda i: book_session(
                trainer=coaches[i],
                member=members[i],
                on=self.day,
                start_time=time(9),
                end_time=time(10),
            ),
            count=2,
        )
        self.assertEqual(len(winners(results)), 2)

    def test_a_cancelled_slot_can_be_rebooked_once(self):
        # The index counts only live bookings, so a cancellation frees the
        # slot -- and the next race for it must still resolve to one winner.
        first = self._book(make_user("conc_l"), time(9), time(10))
        cancel_session(first)

        members = [make_user("conc_m"), make_user("conc_n")]
        results = run_concurrently(
            lambda i: self._book(members[i], time(9), time(10)), count=2
        )
        self.assertEqual(len(winners(results)), 1)
        self.assertEqual(self._live().count(), 1)

    def test_a_member_cannot_be_in_two_places_at_once(self):
        """The same rule, seen from the member's side.

        Two different trainers booked for one member at the same hour share no
        trainer, so locking the trainer's sessions never serialised them and
        the member ended up owing two sessions at 09:00. Locking the member row
        as well as the trainer's is what closes it.
        """
        other = make_user("conc_coach3", Role.TRAINER)
        Availability.objects.create(
            trainer=other, weekday=2, start_time=time(9), end_time=time(17)
        )
        coaches = [self.trainer, other]
        # One member per attempt, created up front: making them inside the
        # race would have the two threads collide on the username instead of
        # on the booking, and the test would pass for the wrong reason.
        members = [make_user(f"two_places_{n}") for n in range(ATTEMPTS)]

        doubled = self._race_repeatedly(
            lambda attempt, i: book_session(
                trainer=coaches[i],
                member=members[attempt],
                on=self.day,
                start_time=time(9),
                end_time=time(10),
            )
        )
        self.assertEqual(
            doubled, 0, f"{doubled}/{ATTEMPTS} races booked one member with two trainers"
        )

    def test_an_overlap_is_caught_once_the_day_has_any_booking(self):
        """The other half of the bug above, and the proof of its mechanism.

        One unrelated 15:00 booking gives `select_for_update()` a row to hold,
        and the same overlapping race is then refused correctly. So the lock
        works exactly when there is something to lock -- which is why the empty
        day is the hole.
        """
        self._book(make_user("probe_seed"), time(15), time(16))
        members = [make_user("probe_a"), make_user("probe_b")]
        windows = [(time(9), time(10)), (time(9, 30), time(10, 30))]
        results = run_concurrently(lambda i: self._book(members[i], *windows[i]), count=2)

        self.assertEqual(len(winners(results)), 1)
        self.assertEqual(self._live().count(), 2)  # the 15:00 seed plus one winner
