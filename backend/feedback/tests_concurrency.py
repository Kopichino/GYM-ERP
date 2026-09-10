"""One feedback response per occasion, under genuine concurrency.

A double-tapped Send is the ordinary way this rule gets tested in production,
and it is a race: both taps read "no response yet" before either writes. Two
rows would count one member's opinion twice, which quietly moves every NPS and
promoter figure derived from the table.

The rule is a pair of partial unique indexes -- one per visit, one per PT
session -- so unlike the PT overlap case there is no lock involved. It still
needs a backend that runs two writers at once to be worth testing.
"""

from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from accounts.models import MemberProfile, Role
from attendance.models import CheckInOut
from core.testing import losers, requires_row_locks, run_concurrently, winners
from pt.models import PTSession, SessionStatus

from .models import Survey, SurveyResponse, Trigger

User = get_user_model()


def make_user(username, role=Role.MEMBER):
    user = User.objects.create_user(
        username=username, email=f"{username}@example.com", password="pass12345", role=role
    )
    if role == Role.MEMBER:
        MemberProfile.objects.get_or_create(user=user)
    return user


def respond(**kwargs):
    """Create a response the way the endpoint does, so the constraint is what
    refuses the duplicate rather than a check in the test."""
    with transaction.atomic():
        return SurveyResponse.objects.create(**kwargs)


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
class ConcurrentVisitResponseTests(_ScopedTransactionTestCase):
    # No reset_sequences: the tenancy fixtures insert an Organisation, and
    # resetting the sequence hands that id out a second time. Nothing here
    # depends on primary key values.

    def setUp(self):
        super().setUp()
        self.member = make_user("fb_conc_member")
        self.survey = Survey.objects.create(
            title="How was it?", question="Rate your session", trigger=Trigger.POST_CHECKIN
        )
        self.visit = CheckInOut.objects.create(user=self.member)

    def test_a_double_tapped_send_records_one_answer(self):
        results = run_concurrently(
            lambda _: respond(
                survey=self.survey, member=self.member, score=9, visit=self.visit
            ),
            count=2,
        )

        self.assertEqual(len(winners(results)), 1)
        self.assertEqual(SurveyResponse.objects.filter(visit=self.visit).count(), 1)
        self.assertTrue(all(isinstance(e, IntegrityError) for e in losers(results)))

    def test_a_burst_of_taps_still_records_one(self):
        run_concurrently(
            lambda _: respond(
                survey=self.survey, member=self.member, score=8, visit=self.visit
            ),
            count=6,
        )
        self.assertEqual(SurveyResponse.objects.filter(visit=self.visit).count(), 1)

    def test_two_visits_may_each_be_answered(self):
        # The rule is per occasion, not per member: someone who trains twice
        # gets asked twice, and both answers must land.
        #
        # The first visit has to be closed before the second opens -- a member
        # can only have one open check-in, which is the invariant next door.
        self.visit.check_out_time = timezone.now()
        self.visit.save(update_fields=["check_out_time"])
        second = CheckInOut.objects.create(user=self.member)
        visits = [self.visit, second]

        results = run_concurrently(
            lambda i: respond(
                survey=self.survey, member=self.member, score=7, visit=visits[i]
            ),
            count=2,
        )
        self.assertEqual(len(winners(results)), 2)

    def test_two_surveys_may_each_be_answered_for_one_visit(self):
        # The index is on (survey, visit), so a second survey about the same
        # visit is a different occasion and must not be blocked. It has to sit
        # on another trigger: only one survey per trigger may be active.
        other = Survey.objects.create(
            title="Cleanliness", question="Was the gym clean?", trigger=Trigger.MANUAL
        )
        surveys = [self.survey, other]

        results = run_concurrently(
            lambda i: respond(
                survey=surveys[i], member=self.member, score=6, visit=self.visit
            ),
            count=2,
        )
        self.assertEqual(len(winners(results)), 2)

    def test_a_manual_response_has_no_occasion_to_collide_on(self):
        # Null visit and null pt_session: NULLs are distinct in a unique index,
        # so manual answers deliberately do not participate in the rule.
        manual = Survey.objects.create(
            title="Anything else?", question="Tell us more", trigger=Trigger.MANUAL
        )
        results = run_concurrently(
            lambda _: respond(survey=manual, member=self.member, score=5), count=3
        )
        self.assertEqual(len(winners(results)), 3)


@requires_row_locks
@requires_row_locks
class ConcurrentPtResponseTests(_ScopedTransactionTestCase):
    # No reset_sequences: the tenancy fixtures insert an Organisation, and
    # resetting the sequence hands that id out a second time. Nothing here
    # depends on primary key values.

    def setUp(self):
        super().setUp()
        self.member = make_user("fb_conc_pt_member")
        self.trainer = make_user("fb_conc_pt_coach", Role.TRAINER)
        self.survey = Survey.objects.create(
            title="Session feedback", question="Rate your trainer", trigger=Trigger.POST_PT
        )
        self.session = PTSession.objects.create(
            trainer=self.trainer,
            member=self.member,
            date=timezone.localdate() + timedelta(days=1),
            start_time=time(9),
            end_time=time(10),
            booked_by=self.member,
            status=SessionStatus.BOOKED,
        )

    def test_a_double_tapped_send_records_one_answer(self):
        results = run_concurrently(
            lambda _: respond(
                survey=self.survey,
                member=self.member,
                score=10,
                pt_session=self.session,
            ),
            count=2,
        )

        self.assertEqual(len(winners(results)), 1)
        self.assertEqual(
            SurveyResponse.objects.filter(pt_session=self.session).count(), 1
        )

    def test_the_two_indexes_do_not_interfere(self):
        # A visit response and a PT response written at the same instant are
        # different occasions on different indexes; both must land.
        visit = CheckInOut.objects.create(user=self.member)
        visit_survey = Survey.objects.create(
            title="Visit", question="How was your visit?", trigger=Trigger.POST_CHECKIN
        )

        def write(i):
            if i == 0:
                return respond(
                    survey=visit_survey, member=self.member, score=9, visit=visit
                )
            return respond(
                survey=self.survey, member=self.member, score=9, pt_session=self.session
            )

        results = run_concurrently(write, count=2)
        self.assertEqual(len(winners(results)), 2)
