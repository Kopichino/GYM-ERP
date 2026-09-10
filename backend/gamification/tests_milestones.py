"""Milestone badges, the new-PR moment, and the private "just for me" standing."""

from datetime import date, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.test import APITestCase

from core.testing import TenantAPIMixin

from accounts.models import MemberProfile, Role
from attendance.models import CheckInOut
from bodystats.models import BodyMeasurement
from schedule_app.models import BookingStatus, ClassBooking, ClassSession
from workouts.models import Exercise, WorkoutLog, WorkoutSession

from . import awards, celebrations, leaderboard, records
from .models import Badge, Criterion, GamificationProfile, PersonalRecord, Tier

User = get_user_model()
TODAY = timezone.localdate()


def make_member(username, joined_days_ago=400):
    user = User.objects.create_user(
        username=username, email=f"{username}@example.com", password="pass12345",
        role=Role.MEMBER,
    )
    MemberProfile.objects.get_or_create(user=user)
    MemberProfile.objects.filter(user=user).update(
        join_date=TODAY - timedelta(days=joined_days_ago)
    )
    # Re-fetched: creating the profile populated the reverse one-to-one cache,
    # so the original instance still carries the join date just replaced.
    return User.objects.get(pk=user.pk)


def log_set(member, exercise, weight, reps=5, days_ago=0, unit="kg"):
    session = WorkoutSession.objects.create(user=member)
    WorkoutSession.objects.filter(pk=session.pk).update(
        date=TODAY - timedelta(days=days_ago)
    )
    session.refresh_from_db()
    return WorkoutLog.objects.create(
        session=session, exercise=exercise, set_number=1, reps=reps,
        weight=Decimal(str(weight)), weight_unit=unit,
    )


def weigh(member, kg, days_ago=0):
    return BodyMeasurement.objects.create(
        user=member, weight_kg=Decimal(str(kg)),
        recorded_on=TODAY - timedelta(days=days_ago),
    )


def visit_on_date(member, day):
    """A finished visit on a specific day.

    Closed on creation so the one-open-check-in index -- which none of this
    feature touches -- is never left holding a row open.
    """
    when = timezone.make_aware(
        timezone.datetime.combine(day, time(12, 0)), timezone.get_current_timezone()
    )
    visit = CheckInOut.objects.create(user=member, check_out_time=when)
    CheckInOut.objects.filter(pk=visit.pk).update(
        check_in_time=when, check_out_time=when + timedelta(hours=1)
    )
    return visit


def month_before(day, months):
    """The 15th of the month `months` before `day`'s month.

    Explicit month arithmetic rather than a day offset: "35 days ago" lands in
    the month before last whenever February is involved, which would make a
    consecutive-months test fail for a few days each spring.
    """
    year, month = day.year, day.month - months
    while month < 1:
        month += 12
        year -= 1
    return date(year, month, 15)


class LiftBadgeTests(TenantAPIMixin, APITestCase):
    """"First 100kg squat" -- a weight, on one named exercise."""

    def setUp(self):
        from core.testing import founding_tenant

        # Badge uniqueness is per organisation, and a null organisation cannot
        # collide with anything -- NULLs are distinct in a unique index.
        self.org, _ = founding_tenant()
        self.member = make_member("milestoner")
        self.squat = Exercise.objects.create(name="Back Squat", muscle_group="Legs")
        self.bench = Exercise.objects.create(name="Bench Press", muscle_group="Chest")

    def lift_badge(self, exercise, kg, code):
        return Badge.objects.create(
            code=code, name=f"{kg}kg {exercise.name}", criterion=Criterion.LIFT,
            exercise=exercise, threshold=kg, tier=Tier.GOLD, organisation=self.org,
        )

    def test_a_first_hundred_kilo_squat_earns_its_badge(self):
        badge = self.lift_badge(self.squat, 100, "squat-100")
        log_set(self.member, self.squat, 102.5, days_ago=1)
        records.sync_records(self.member)

        awarded = awards.evaluate(self.member)
        self.assertEqual([row.badge for row in awarded], [badge])
        self.assertEqual(awarded[0].value_at_award, 102)

    def test_the_same_weight_on_another_lift_does_not(self):
        """100kg is a milestone on the squat and a different one on the bench."""
        self.lift_badge(self.squat, 100, "squat-100")
        log_set(self.member, self.bench, 105, days_ago=1)
        records.sync_records(self.member)
        self.assertEqual(awards.evaluate(self.member), [])

    def test_pounds_are_converted_before_the_comparison(self):
        self.lift_badge(self.squat, 100, "squat-100")
        # 225 lb is 102.06 kg.
        log_set(self.member, self.squat, 225, days_ago=1, unit="lb")
        records.sync_records(self.member)
        self.assertEqual(len(awards.evaluate(self.member)), 1)

    def test_falling_short_earns_nothing(self):
        self.lift_badge(self.squat, 100, "squat-100")
        log_set(self.member, self.squat, 97.5, days_ago=1)
        records.sync_records(self.member)
        self.assertEqual(awards.evaluate(self.member), [])

    def test_a_lift_badge_must_name_an_exercise(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Badge.objects.create(
                    code="floating-100", name="100kg", criterion=Criterion.LIFT,
                    threshold=100,
                )

    def test_a_counting_badge_must_not(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Badge.objects.create(
                    code="visits-with-exercise", name="50 visits",
                    criterion=Criterion.VISITS, threshold=50, exercise=self.squat,
                )

    def test_two_counting_badges_still_cannot_share_a_threshold(self):
        """The original rule, unchanged by making room for lift badges."""
        Badge.objects.create(
            code="visits-50", name="50 visits", criterion=Criterion.VISITS,
            threshold=50, organisation=self.org,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Badge.objects.create(
                    code="visits-50-again", name="Fifty visits",
                    criterion=Criterion.VISITS, threshold=50, organisation=self.org,
                )

    def test_but_two_lifts_at_the_same_weight_can_coexist(self):
        self.lift_badge(self.squat, 100, "squat-100")
        self.lift_badge(self.bench, 100, "bench-100")
        self.assertEqual(Badge.objects.filter(criterion=Criterion.LIFT).count(), 2)

    def test_one_exercise_cannot_have_the_same_weight_twice(self):
        self.lift_badge(self.squat, 100, "squat-100")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.lift_badge(self.squat, 100, "squat-100-again")


class ClassBadgeTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.member = make_member("classgoer")

    def booking(self, status, days_ago):
        session = ClassSession.objects.create(
            title=f"Class {days_ago}", date=TODAY - timedelta(days=days_ago),
            start_time=time(9), end_time=time(10), capacity=10,
        )
        return ClassBooking.objects.create(
            member=self.member, session=session, status=status
        )

    def test_only_the_ones_marked_off_count(self):
        Badge.objects.create(
            code="classes-2", name="2 classes", criterion=Criterion.CLASSES, threshold=2
        )
        self.booking(BookingStatus.ATTENDED, 1)
        self.booking(BookingStatus.ATTENDED, 2)
        self.booking(BookingStatus.BOOKED, 3)

        self.assertEqual(awards.current_values(self.member)[Criterion.CLASSES], 2)
        self.assertEqual(len(awards.evaluate(self.member)), 1)

    def test_a_booking_never_marked_off_is_not_an_attendance(self):
        """Otherwise it is a badge for booking classes, not for going to them."""
        self.booking(BookingStatus.BOOKED, 1)
        self.assertEqual(awards.current_values(self.member)[Criterion.CLASSES], 0)

    def test_a_cancelled_booking_certainly_is_not(self):
        self.booking(BookingStatus.CANCELLED, 1)
        self.assertEqual(awards.current_values(self.member)[Criterion.CLASSES], 0)


class MonthStreakTests(TenantAPIMixin, APITestCase):
    """A six-month streak has to mean months, not 180 days in a row."""

    def test_consecutive_months_with_a_visit(self):
        dates = [date(2026, 1, 5), date(2026, 2, 20), date(2026, 3, 1)]
        self.assertEqual(awards.month_streak(dates), 3)

    def test_a_missed_month_breaks_it(self):
        dates = [date(2026, 1, 5), date(2026, 3, 1), date(2026, 4, 2)]
        self.assertEqual(awards.month_streak(dates), 2)

    def test_the_longest_run_wins_not_the_latest(self):
        dates = [
            date(2026, 1, 5), date(2026, 2, 5), date(2026, 3, 5),  # three
            date(2026, 7, 5), date(2026, 8, 5),                     # two
        ]
        self.assertEqual(awards.month_streak(dates), 3)

    def test_it_rolls_over_a_year_boundary(self):
        self.assertEqual(
            awards.month_streak([date(2025, 12, 30), date(2026, 1, 2)]), 2
        )

    def test_many_visits_in_one_month_are_still_one_month(self):
        dates = [date(2026, 1, day) for day in (1, 8, 15, 22, 29)]
        self.assertEqual(awards.month_streak(dates), 1)

    def test_nobody_who_has_never_been_has_a_streak(self):
        self.assertEqual(awards.month_streak([]), 0)

    def test_the_badge_is_earned_off_real_visits(self):
        member = make_member("monthly")
        Badge.objects.create(
            code="months-3", name="Three months running",
            criterion=Criterion.MONTH_STREAK, threshold=3,
        )
        for months_back in (0, 1, 2):
            visit_on_date(member, month_before(TODAY, months_back))

        self.assertEqual(awards.current_values(member)[Criterion.MONTH_STREAK], 3)
        self.assertEqual(len(awards.evaluate(member)), 1)


class PRCelebrationTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.member = make_member("prwinner")
        self.squat = Exercise.objects.create(name="Back Squat", muscle_group="Legs")

    def test_a_fresh_record_is_waiting_to_be_celebrated(self):
        log_set(self.member, self.squat, 100, days_ago=1)
        pending = celebrations.pending(self.member)
        self.assertEqual(len(pending), 1)
        self.assertTrue(pending[0]["is_first"])
        self.assertIsNone(pending[0]["previous_kg"])

    def test_beating_it_says_by_how_much(self):
        log_set(self.member, self.squat, 100, days_ago=3)
        log_set(self.member, self.squat, 110, days_ago=1)
        newest = celebrations.pending(self.member)[0]
        self.assertFalse(newest["is_first"])
        self.assertEqual(newest["previous_kg"], Decimal("100.00"))
        self.assertEqual(newest["gain_kg"], Decimal("10.00"))

    def test_a_set_that_does_not_beat_the_best_is_not_a_record_at_all(self):
        log_set(self.member, self.squat, 110, days_ago=3)
        log_set(self.member, self.squat, 100, days_ago=1)
        self.assertEqual(len(celebrations.pending(self.member)), 1)

    def test_old_history_arrives_already_seen(self):
        """Importing a back catalogue must not fire fifty party poppers."""
        log_set(self.member, self.squat, 80, days_ago=200)
        log_set(self.member, self.squat, 90, days_ago=150)
        log_set(self.member, self.squat, 100, days_ago=100)

        self.assertEqual(celebrations.pending(self.member), [])
        self.assertEqual(PersonalRecord.objects.filter(member=self.member).count(), 3)

    def test_and_a_new_one_on_top_of_that_history_still_fires(self):
        log_set(self.member, self.squat, 100, days_ago=100)
        log_set(self.member, self.squat, 110, days_ago=1)
        pending = celebrations.pending(self.member)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["weight_kg"], Decimal("110.00"))

    def test_marking_it_seen_stops_it_coming_back(self):
        log_set(self.member, self.squat, 100, days_ago=1)
        self.assertEqual(len(celebrations.pending(self.member)), 1)
        celebrations.mark_seen(self.member)
        self.assertEqual(celebrations.pending(self.member), [])

    def test_a_resync_does_not_unsee_it(self):
        """sync_records reuses the row, so the acknowledgement has to survive."""
        log_set(self.member, self.squat, 100, days_ago=1)
        celebrations.pending(self.member)
        celebrations.mark_seen(self.member)
        records.sync_records(self.member)
        records.sync_records(self.member)
        self.assertEqual(celebrations.pending(self.member), [])

    def test_one_member_cannot_acknowledge_anothers(self):
        other = make_member("prother")
        log_set(other, self.squat, 100, days_ago=1)
        records.sync_records(other)
        record = PersonalRecord.objects.get(member=other)

        celebrations.mark_seen(self.member, [record.id])
        record.refresh_from_db()
        self.assertIsNone(record.seen_at)


class PrivateStandingTests(TenantAPIMixin, APITestCase):
    """The just-for-me mode: a position, and nobody else's name."""

    def setUp(self):
        self.squat = Exercise.objects.create(name="Back Squat", muscle_group="Legs")
        self.me = make_member("standing-me")

    def lifter(self, name, weight, bodyweight):
        member = make_member(name)
        weigh(member, bodyweight, days_ago=3)
        log_set(member, self.squat, weight, days_ago=1)
        records.sync_records(member)
        return member

    def build_pool(self, size, base=100):
        for index in range(size):
            self.lifter(f"pool{index}", base + index * 5, 80)

    def my_lift(self, weight, bodyweight=80):
        weigh(self.me, bodyweight, days_ago=3)
        log_set(self.me, self.squat, weight, days_ago=1)
        records.sync_records(self.me)

    def test_a_pool_that_small_refuses_to_place_anyone(self):
        """Top third of three, in a gym where everyone knows who trains, is a name."""
        self.my_lift(120)
        self.build_pool(2)

        standing = leaderboard.my_standing(self.me, self.squat.id)
        self.assertEqual(standing["pool"], 3)
        self.assertIsNone(standing["top_percent"])
        self.assertIn("too few", standing["reason"])

    def test_a_big_enough_pool_gives_a_rank_and_a_percentile(self):
        self.my_lift(200)
        self.build_pool(9)

        standing = leaderboard.my_standing(self.me, self.squat.id)
        self.assertEqual(standing["pool"], 10)
        self.assertEqual(standing["rank"], 1)
        self.assertEqual(standing["top_percent"], 10)
        self.assertEqual(standing["better_than"], 90)

    def test_the_weakest_lifter_is_placed_last(self):
        self.my_lift(50)
        self.build_pool(9)

        standing = leaderboard.my_standing(self.me, self.squat.id)
        self.assertEqual(standing["rank"], 10)
        self.assertEqual(standing["top_percent"], 100)
        self.assertEqual(standing["better_than"], 0)

    def test_it_never_names_anybody_else(self):
        self.my_lift(100)
        self.build_pool(9)

        body = str(leaderboard.my_standing(self.me, self.squat.id))
        for index in range(9):
            self.assertNotIn(f"pool{index}", body)

    def test_opting_out_of_the_public_board_does_not_cost_the_private_one(self):
        """The whole point: no name published, still able to see the trend."""
        GamificationProfile.objects.update_or_create(
            user=self.me, defaults={"leaderboard_opt_in": False}
        )
        self.my_lift(200)
        self.build_pool(9)

        self.assertEqual(leaderboard.my_standing(self.me, self.squat.id)["rank"], 1)
        public = leaderboard.board(exercise_id=self.squat.id)["rows"]
        self.assertNotIn(self.me.username, [row["username"] for row in public])

    def test_a_member_with_no_scored_lift_is_told_why(self):
        self.build_pool(9)
        standing = leaderboard.my_standing(self.me, self.squat.id)
        self.assertIsNone(standing["ratio"])
        self.assertIsNone(standing["rank"])
        self.assertIn("weighed", standing["reason"])

    def test_an_unweighed_lift_scores_nobody(self):
        log_set(self.me, self.squat, 200, days_ago=1)
        records.sync_records(self.me)
        self.build_pool(9)
        self.assertIsNone(leaderboard.my_standing(self.me, self.squat.id)["ratio"])


class NewEndpointTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.member = make_member("endpoints")
        self.squat = Exercise.objects.create(name="Back Squat", muscle_group="Legs")
        self.client.force_authenticate(self.member)

    def test_the_celebration_feed_and_acknowledging_it(self):
        log_set(self.member, self.squat, 100, days_ago=1)
        listed = self.client.get("/api/gamification/records/new/")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.data), 1)

        acked = self.client.post(
            "/api/gamification/records/new/",
            {"ids": [listed.data[0]["id"]]},
            format="json",
        )
        self.assertEqual(acked.data["seen"], 1)
        self.assertEqual(len(self.client.get("/api/gamification/records/new/").data), 0)

    def test_the_feed_is_empty_for_someone_who_has_lifted_nothing(self):
        self.assertEqual(self.client.get("/api/gamification/records/new/").data, [])

    def test_the_private_standing_needs_an_exercise(self):
        self.assertEqual(
            self.client.get("/api/gamification/leaderboard/me/").status_code, 400
        )

    def test_the_private_standing_answers_for_the_caller(self):
        weigh(self.member, 80, days_ago=3)
        log_set(self.member, self.squat, 120, days_ago=1)
        resp = self.client.get(
            f"/api/gamification/leaderboard/me/?exercise={self.squat.id}"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["exercise_id"], self.squat.id)

    def test_a_signed_out_visitor_gets_nothing(self):
        self.client.force_authenticate(None)
        self.assertEqual(
            self.client.get("/api/gamification/records/new/").status_code, 401
        )
        self.assertEqual(
            self.client.get("/api/gamification/leaderboard/me/").status_code, 401
        )


class BadgeFormValidationTests(TenantAPIMixin, APITestCase):
    """A mis-specified badge gets a sentence, not a 500 off the constraint."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username="badgeadmin", email="ba@example.com", password="pass12345",
            role=Role.ADMIN,
        )
        self.squat = Exercise.objects.create(name="Back Squat", muscle_group="Legs")
        self.client.force_authenticate(self.admin)

    def test_a_lift_badge_with_no_exercise_is_explained(self):
        resp = self.client.post(
            "/api/gamification/badges/",
            {"code": "lift-100", "name": "100kg", "criterion": "lift", "threshold": 100},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("which exercise", str(resp.data["exercise"]))

    def test_a_counting_badge_with_one_is_too(self):
        resp = self.client.post(
            "/api/gamification/badges/",
            {
                "code": "visits-50", "name": "50 visits", "criterion": "visits",
                "threshold": 50, "exercise": self.squat.id,
            },
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Only a lift badge", str(resp.data["exercise"]))

    def test_a_well_formed_lift_badge_is_accepted(self):
        resp = self.client.post(
            "/api/gamification/badges/",
            {
                "code": "squat-100", "name": "100kg Squat", "criterion": "lift",
                "threshold": 100, "exercise": self.squat.id,
            },
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["exercise_name"], "Back Squat")
