"""Badge progress at the endpoint, checked against independently counted data.

Progress is derived on read from visits, sessions, sets, records and class
attendance. Every test here seeds a known number of those, works out the
percentage by hand, and asserts the achievements screen reports the same. A
status-code assertion would sit happily on top of a badge that says 33% when
the member is at 66%, and the number is the whole feature.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from core.testing import TenantAPIMixin

from accounts.models import MemberProfile, Role
from attendance.models import CheckInOut
from workouts.models import Exercise, WorkoutLog, WorkoutSession

from .models import Badge, Criterion, Tier

User = get_user_model()
TODAY = timezone.localdate()


def make_member(username, joined_days_ago=400):
    user = User.objects.create_user(
        username=username, email=f"{username}@example.com", password="pass12345", role=Role.MEMBER
    )
    MemberProfile.objects.get_or_create(user=user)
    MemberProfile.objects.filter(user=user).update(
        join_date=TODAY - timedelta(days=joined_days_ago)
    )
    return User.objects.get(pk=user.pk)


class BadgeProgressEndpointTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.member = make_member("prog_member")
        self.client.force_authenticate(self.member)

    def _visit(self, days_ago):
        visit = CheckInOut.objects.create(user=self.member)
        stamp = timezone.now() - timedelta(days=days_ago)
        CheckInOut.objects.filter(pk=visit.pk).update(
            check_in_time=stamp, check_out_time=stamp
        )
        return visit

    def _badge(self, code, criterion, threshold, **kwargs):
        return Badge.objects.create(
            code=code,
            name=code.replace("-", " ").title(),
            criterion=criterion,
            threshold=threshold,
            tier=kwargs.pop("tier", Tier.BRONZE),
            **kwargs,
        )

    def _row(self, code):
        data = self.client.get("/api/gamification/achievements/").data
        return next(r for r in data["badges"] if r["badge"]["code"] == code)

    def test_percent_is_the_count_over_the_threshold(self):
        self._badge("visits-10", Criterion.VISITS, 10)
        for day in range(1, 5):  # four distinct days
            self._visit(day)

        row = self._row("visits-10")
        # 4 of 10 -> 40%, worked out here rather than read off the response.
        self.assertEqual(row["value"], 4)
        self.assertEqual(row["threshold"], 10)
        self.assertEqual(row["percent"], round(4 * 100 / 10))
        self.assertFalse(row["earned"])

    def test_two_visits_in_one_day_count_once(self):
        # The criterion is distinct days: someone who nips out at lunch and
        # comes back has been to the gym once, and a badge that counted rows
        # would hand out a ten-visit award to someone who came five times.
        self._badge("visits-10", Criterion.VISITS, 10)
        self._visit(3)
        self._visit(3)
        self._visit(2)

        row = self._row("visits-10")
        self.assertEqual(row["value"], 2)
        self.assertEqual(row["percent"], round(2 * 100 / 10))

    def test_percent_is_capped_at_a_hundred(self):
        self._badge("visits-2", Criterion.VISITS, 2)
        for day in range(1, 8):
            self._visit(day)

        row = self._row("visits-2")
        # 7 visits against a threshold of 2 is 350%, which is not a progress bar.
        self.assertEqual(row["percent"], 100)
        self.assertTrue(row["earned"])

    def test_an_earned_badge_freezes_the_number_it_was_earned_at(self):
        self._badge("visits-3", Criterion.VISITS, 3)
        for day in (5, 4, 3):
            self._visit(day)
        self.client.get("/api/gamification/achievements/")  # awards it

        self._visit(1)
        row = self._row("visits-3")
        self.assertTrue(row["earned"])
        self.assertEqual(row["value"], 3, "an earned badge kept climbing after the fact")
        self.assertIsNotNone(row["awarded_on"])

    def test_sets_and_sessions_are_counted_separately(self):
        bench = Exercise.objects.create(name="Bench", muscle_group="Chest")
        self._badge("sessions-4", Criterion.WORKOUTS, 4)
        self._badge("sets-10", Criterion.SETS, 10)

        for _ in range(2):
            session = WorkoutSession.objects.create(user=self.member)
            for set_number in range(1, 4):
                WorkoutLog.objects.create(
                    session=session,
                    exercise=bench,
                    set_number=set_number,
                    weight=50,
                    reps=5,
                )

        # 2 sessions, 6 sets -- one badge must not read the other's number.
        self.assertEqual(self._row("sessions-4")["value"], 2)
        self.assertEqual(self._row("sets-10")["value"], 6)
        self.assertEqual(self._row("sessions-4")["percent"], round(2 * 100 / 4))
        self.assertEqual(self._row("sets-10")["percent"], round(6 * 100 / 10))

    def test_months_as_a_member_comes_from_the_join_date(self):
        member = make_member("prog_veteran", joined_days_ago=400)
        self.client.force_authenticate(member)
        self._badge("months-6", Criterion.MONTHS, 6)

        row = self._row("months-6")
        # 400 days is thirteen whole months.
        self.assertEqual(row["value"], 13)
        self.assertEqual(row["percent"], 100)

    def test_an_inactive_badge_is_not_offered_at_all(self):
        # Different thresholds: one badge per (criterion, threshold) whether or
        # not it is active, so a retired badge still occupies its number.
        self._badge("retired", Criterion.VISITS, 5, is_active=False)
        self._badge("live", Criterion.VISITS, 6)

        codes = {
            r["badge"]["code"]
            for r in self.client.get("/api/gamification/achievements/").data["badges"]
        }
        self.assertIn("live", codes)
        self.assertNotIn("retired", codes)

    def test_the_headline_counts_match_the_rows(self):
        self._badge("visits-1", Criterion.VISITS, 1)
        self._badge("visits-99", Criterion.VISITS, 99)
        self._visit(1)

        data = self.client.get("/api/gamification/achievements/").data
        # Counted from the rows themselves, not trusted from the summary.
        earned = sum(1 for row in data["badges"] if row["earned"])
        self.assertEqual(data["earned_count"], earned)
        self.assertEqual(data["badge_count"], len(data["badges"]))
        self.assertEqual(data["total_visits"], 1)

    def test_progress_is_scoped_to_the_caller(self):
        self._badge("visits-10", Criterion.VISITS, 10)
        stranger = make_member("prog_stranger")
        for day in range(1, 6):
            visit = CheckInOut.objects.create(user=stranger)
            stamp = timezone.now() - timedelta(days=day)
            CheckInOut.objects.filter(pk=visit.pk).update(
                check_in_time=stamp, check_out_time=stamp
            )

        # Someone else's five visits must not show on this member's ladder.
        self.assertEqual(self._row("visits-10")["value"], 0)

    def test_a_member_with_nothing_logged_reads_zero_not_an_error(self):
        self._badge("visits-10", Criterion.VISITS, 10)
        row = self._row("visits-10")
        self.assertEqual(row["value"], 0)
        self.assertEqual(row["percent"], 0)
        self.assertFalse(row["earned"])

    def test_earned_badges_sort_ahead_of_locked_ones(self):
        self._badge("visits-1", Criterion.VISITS, 1)
        self._badge("visits-50", Criterion.VISITS, 50)
        self._visit(1)

        rows = self.client.get("/api/gamification/achievements/").data["badges"]
        earned_positions = [i for i, r in enumerate(rows) if r["earned"]]
        locked_positions = [i for i, r in enumerate(rows) if not r["earned"]]
        self.assertTrue(
            not earned_positions or not locked_positions
            or max(earned_positions) < min(locked_positions)
        )
