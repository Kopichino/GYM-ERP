from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from core.testing import TenantAPIMixin

from accounts.models import MemberProfile, Role
from attendance.models import CheckInOut
from bodystats.models import BodyMeasurement
from workouts.models import Exercise, WorkoutLog, WorkoutSession

from . import awards, leaderboard, records
from .models import (
    Badge,
    Criterion,
    GamificationProfile,
    MemberBadge,
    PersonalRecord,
    Tier,
)

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
    # Re-fetched, not returned as-is: creating the profile populates the
    # reverse one-to-one cache on `user`, so the instance would still be
    # carrying the join date the queryset update just replaced.
    return User.objects.get(pk=user.pk)


def log_set(member, exercise, weight, reps=5, days_ago=0, unit="kg"):
    """A logged set on a given day. `WorkoutSession.date` is auto_now_add, so
    it has to be forced past the default."""
    session = WorkoutSession.objects.create(user=member)
    WorkoutSession.objects.filter(pk=session.pk).update(
        date=TODAY - timedelta(days=days_ago)
    )
    session.refresh_from_db()
    return WorkoutLog.objects.create(
        session=session,
        exercise=exercise,
        set_number=1,
        reps=reps,
        weight=Decimal(str(weight)),
        weight_unit=unit,
    )


def weigh(member, kg, days_ago=0):
    return BodyMeasurement.objects.create(
        user=member, weight_kg=Decimal(str(kg)), recorded_on=TODAY - timedelta(days=days_ago)
    )


class RecordSnapshotTests(TenantAPIMixin, APITestCase):
    """The point of the whole feature: a PR is scored against the bodyweight
    the member had when they lifted it."""

    def setUp(self):
        self.member = make_member("lifter")
        self.squat = Exercise.objects.create(name="Squat", muscle_group="Legs")

    def test_bodyweight_is_taken_from_the_time_of_the_lift(self):
        weigh(self.member, 100, days_ago=200)
        log_set(self.member, self.squat, 150, days_ago=180)

        record = records.sync_records(self.member).get()
        self.assertEqual(record.bodyweight_kg, Decimal("100.00"))
        self.assertEqual(record.ratio, Decimal("1.50"))

    def test_losing_weight_later_does_not_improve_an_old_record(self):
        """Dividing by *current* bodyweight would rewrite history."""
        weigh(self.member, 100, days_ago=200)
        log_set(self.member, self.squat, 150, days_ago=180)
        records.sync_records(self.member)

        weigh(self.member, 80, days_ago=1)
        records.sync_records(self.member)

        record = PersonalRecord.objects.get(member=self.member)
        self.assertEqual(record.bodyweight_kg, Decimal("100.00"))
        self.assertEqual(record.ratio, Decimal("1.50"))

    def test_a_later_weigh_in_is_never_used_for_an_earlier_lift(self):
        # Only weigh-in is *after* the lift, so there is nothing honest to use.
        log_set(self.member, self.squat, 120, days_ago=30)
        weigh(self.member, 90, days_ago=1)

        record = records.sync_records(self.member).get()
        self.assertIsNone(record.bodyweight_kg)
        self.assertIsNone(record.ratio)

    def test_each_lift_keeps_its_own_snapshot(self):
        weigh(self.member, 100, days_ago=300)
        log_set(self.member, self.squat, 140, days_ago=250)
        weigh(self.member, 90, days_ago=100)
        log_set(self.member, self.squat, 160, days_ago=50)

        records.sync_records(self.member)
        by_date = {r.achieved_on: r for r in PersonalRecord.objects.filter(member=self.member)}
        self.assertEqual(by_date[TODAY - timedelta(days=250)].bodyweight_kg, Decimal("100.00"))
        self.assertEqual(by_date[TODAY - timedelta(days=50)].bodyweight_kg, Decimal("90.00"))

    def test_pounds_are_normalised_before_lifts_are_compared(self):
        weigh(self.member, 100, days_ago=30)
        log_set(self.member, self.squat, 100, days_ago=20)  # 100 kg
        log_set(self.member, self.squat, 200, days_ago=10, unit="lb")  # ~90.7 kg

        records.sync_records(self.member)
        # The heavier-looking pound figure is the lighter lift, so it is not a PR.
        self.assertEqual(PersonalRecord.objects.filter(member=self.member).count(), 1)
        self.assertEqual(
            PersonalRecord.objects.get(member=self.member).weight_kg, Decimal("100.00")
        )


class RecordDerivationTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.member = make_member("prlifter")
        self.bench = Exercise.objects.create(name="Bench", muscle_group="Chest")
        weigh(self.member, 80, days_ago=400)

    def test_only_a_set_that_beats_everything_before_it_is_a_record(self):
        log_set(self.member, self.bench, 60, days_ago=30)
        log_set(self.member, self.bench, 50, days_ago=20)
        log_set(self.member, self.bench, 70, days_ago=10)

        records.sync_records(self.member)
        weights = sorted(
            PersonalRecord.objects.filter(member=self.member).values_list("weight_kg", flat=True)
        )
        self.assertEqual(weights, [Decimal("60.00"), Decimal("70.00")])

    def test_one_record_per_day_even_if_they_beat_it_twice(self):
        log_set(self.member, self.bench, 60, days_ago=5)
        log_set(self.member, self.bench, 65, days_ago=5)

        records.sync_records(self.member)
        record = PersonalRecord.objects.get(member=self.member)
        self.assertEqual(record.weight_kg, Decimal("65.00"))

    def test_syncing_twice_changes_nothing(self):
        log_set(self.member, self.bench, 60, days_ago=5)
        records.sync_records(self.member)
        first = list(PersonalRecord.objects.values_list("id", flat=True))
        records.sync_records(self.member)
        self.assertEqual(list(PersonalRecord.objects.values_list("id", flat=True)), first)

    def test_deleting_the_set_removes_the_record(self):
        log = log_set(self.member, self.bench, 60, days_ago=5)
        records.sync_records(self.member)
        self.assertTrue(PersonalRecord.objects.exists())

        log.delete()
        self.assertFalse(PersonalRecord.objects.exists())

    def test_bodyweight_only_movements_are_not_weight_records(self):
        log_set(self.member, self.bench, 0, days_ago=5)
        records.sync_records(self.member)
        self.assertFalse(PersonalRecord.objects.exists())

    def test_records_are_per_exercise(self):
        squat = Exercise.objects.create(name="Squat", muscle_group="Legs")
        log_set(self.member, self.bench, 60, days_ago=10)
        log_set(self.member, squat, 40, days_ago=5)

        records.sync_records(self.member)
        self.assertEqual(PersonalRecord.objects.filter(member=self.member).count(), 2)


class BadgeTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.member = make_member("collector", joined_days_ago=40)
        self.visits_badge = Badge.objects.create(
            code="visits-3", name="Regular", tier=Tier.BRONZE,
            criterion=Criterion.VISITS, threshold=3,
        )

    def visit(self, days_ago):
        record = CheckInOut.objects.create(user=self.member, check_out_time=timezone.now())
        CheckInOut.objects.filter(pk=record.pk).update(
            check_in_time=timezone.now() - timedelta(days=days_ago)
        )

    def test_a_badge_is_awarded_once_the_number_is_reached(self):
        for day in (5, 4, 3):
            self.visit(day)
        awarded = awards.evaluate(self.member)
        self.assertEqual([a.badge.code for a in awarded], ["visits-3"])
        self.assertEqual(MemberBadge.objects.get().value_at_award, 3)

    def test_evaluating_again_awards_nothing_new(self):
        for day in (5, 4, 3):
            self.visit(day)
        awards.evaluate(self.member)
        self.assertEqual(awards.evaluate(self.member), [])
        self.assertEqual(MemberBadge.objects.count(), 1)

    def test_a_badge_is_never_taken_back(self):
        """A badge you can lose in a quiet month is a status bar, not a badge."""
        for day in (5, 4, 3):
            self.visit(day)
        awards.evaluate(self.member)

        CheckInOut.objects.filter(user=self.member).delete()
        awards.evaluate(self.member)
        self.assertTrue(MemberBadge.objects.filter(member=self.member).exists())

    def test_two_check_ins_on_one_day_count_as_one_visit(self):
        self.visit(2)
        self.visit(2)
        self.assertEqual(awards.current_values(self.member)[Criterion.VISITS], 1)

    def test_an_inactive_badge_is_not_awarded(self):
        Badge.objects.update(is_active=False)
        for day in (5, 4, 3):
            self.visit(day)
        self.assertEqual(awards.evaluate(self.member), [])

    def test_months_counts_whole_months_only(self):
        member = make_member("newish", joined_days_ago=20)
        self.assertEqual(awards.current_values(member)[Criterion.MONTHS], 0)

        older = make_member("older", joined_days_ago=200)
        self.assertGreaterEqual(awards.current_values(older)[Criterion.MONTHS], 6)

    def test_progress_shows_locked_badges_with_how_far_along_they_are(self):
        self.visit(1)
        rows = awards.progress(self.member)
        row = next(r for r in rows if r["badge"].code == "visits-3")
        self.assertFalse(row["earned"])
        self.assertEqual(row["value"], 1)
        self.assertEqual(row["percent"], 33)

    def test_an_earned_badge_reports_the_number_it_was_earned_at(self):
        for day in (5, 4, 3):
            self.visit(day)
        awards.evaluate(self.member)
        self.visit(1)

        row = next(r for r in awards.progress(self.member) if r["badge"].code == "visits-3")
        self.assertTrue(row["earned"])
        self.assertEqual(row["value"], 3)


class LeaderboardTests(TenantAPIMixin, APITestCase):
    """Opt-in, monthly, and scored on the snapshot."""

    def setUp(self):
        self.squat = Exercise.objects.create(name="Squat", muscle_group="Legs")
        self.light = make_member("lightlifter")
        self.heavy = make_member("heavylifter")
        for member in (self.light, self.heavy):
            GamificationProfile.objects.create(user=member, leaderboard_opt_in=True)

        # The lighter member lifts less weight but far more of their own.
        weigh(self.light, 60, days_ago=20)
        log_set(self.light, self.squat, 120, days_ago=5)
        weigh(self.heavy, 120, days_ago=20)
        log_set(self.heavy, self.squat, 180, days_ago=5)

        for member in (self.light, self.heavy):
            records.sync_records(member)

    def test_ranked_by_ratio_not_absolute_weight(self):
        rows = leaderboard.board(exercise_id=self.squat.id)["rows"]
        self.assertEqual([r["username"] for r in rows], ["lightlifter", "heavylifter"])
        self.assertEqual(rows[0]["ratio"], Decimal("2.00"))
        self.assertEqual(rows[1]["ratio"], Decimal("1.50"))
        # The heavier absolute lift is still shown; it just does not win.
        self.assertEqual(rows[1]["weight_kg"], Decimal("180.00"))

    def test_a_member_who_has_not_opted_in_is_absent(self):
        GamificationProfile.objects.filter(user=self.light).update(leaderboard_opt_in=False)
        rows = leaderboard.board(exercise_id=self.squat.id)["rows"]
        self.assertEqual([r["username"] for r in rows], ["heavylifter"])

    def test_a_member_with_no_profile_at_all_is_absent(self):
        stranger = make_member("shy")
        weigh(stranger, 70, days_ago=20)
        log_set(stranger, self.squat, 200, days_ago=5)
        records.sync_records(stranger)

        rows = leaderboard.board(exercise_id=self.squat.id)["rows"]
        self.assertNotIn("shy", [r["username"] for r in rows])

    def test_the_board_resets_every_month(self):
        """A lift from an earlier month is not on this month's board."""
        old = make_member("lastmonth")
        GamificationProfile.objects.create(user=old, leaderboard_opt_in=True)
        weigh(old, 70, days_ago=90)
        log_set(old, self.squat, 200, days_ago=45)
        records.sync_records(old)

        rows = leaderboard.board(exercise_id=self.squat.id)["rows"]
        self.assertNotIn("lastmonth", [r["username"] for r in rows])

    def test_a_record_with_no_bodyweight_is_left_off_rather_than_guessed(self):
        unweighed = make_member("unweighed")
        GamificationProfile.objects.create(user=unweighed, leaderboard_opt_in=True)
        log_set(unweighed, self.squat, 300, days_ago=5)
        records.sync_records(unweighed)

        rows = leaderboard.board(exercise_id=self.squat.id)["rows"]
        self.assertNotIn("unweighed", [r["username"] for r in rows])

    def test_only_a_members_best_ratio_that_month_appears(self):
        log_set(self.light, self.squat, 132, days_ago=2)
        records.sync_records(self.light)

        rows = leaderboard.board(exercise_id=self.squat.id)["rows"]
        mine = [r for r in rows if r["username"] == "lightlifter"]
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0]["ratio"], Decimal("2.20"))

    def test_ranks_are_numbered_from_one(self):
        rows = leaderboard.board(exercise_id=self.squat.id)["rows"]
        self.assertEqual([r["rank"] for r in rows], [1, 2])


class GamificationApiTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.member = make_member("apilifter", joined_days_ago=40)
        self.admin = User.objects.create_user(
            username="badgeadmin", email="ba@example.com", password="pass12345", role=Role.ADMIN
        )
        self.squat = Exercise.objects.create(name="Squat", muscle_group="Legs")
        Badge.objects.create(
            code="visits-1", name="First Visit", tier=Tier.BRONZE,
            criterion=Criterion.VISITS, threshold=1,
        )
        self.client.force_authenticate(self.member)

    def test_achievements_awards_on_read(self):
        CheckInOut.objects.create(user=self.member, check_out_time=timezone.now())
        resp = self.client.get("/api/gamification/achievements/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("visits-1", resp.data["newly_awarded"])
        self.assertEqual(resp.data["earned_count"], 1)

    def test_achievements_lists_locked_badges_too(self):
        resp = self.client.get("/api/gamification/achievements/")
        self.assertEqual(resp.data["earned_count"], 0)
        self.assertEqual(len(resp.data["badges"]), 1)
        self.assertFalse(resp.data["badges"][0]["earned"])

    def test_badges_ship_without_artwork(self):
        resp = self.client.get("/api/gamification/badges/")
        self.assertIsNone(resp.data[0]["image"])

    def test_members_cannot_define_a_badge(self):
        resp = self.client.post(
            "/api/gamification/badges/",
            {"code": "mine", "name": "Mine", "criterion": "visits", "threshold": 1},
        )
        self.assertEqual(resp.status_code, 403)

    def test_an_admin_can(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            "/api/gamification/badges/",
            {
                "code": "visits-99",
                "name": "Ninety-nine",
                "tier": Tier.GOLD,
                "criterion": Criterion.VISITS,
                "threshold": 99,
            },
        )
        self.assertEqual(resp.status_code, 201)

    def test_the_leaderboard_is_off_by_default(self):
        resp = self.client.get("/api/gamification/me/")
        self.assertFalse(resp.data["leaderboard_opt_in"])

    def test_a_member_opts_themselves_in(self):
        resp = self.client.patch("/api/gamification/me/", {"leaderboard_opt_in": True})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(GamificationProfile.objects.get(user=self.member).leaderboard_opt_in)

    def test_my_records_are_rebuilt_from_the_log_on_read(self):
        weigh(self.member, 75, days_ago=10)
        log_set(self.member, self.squat, 150, days_ago=5)

        resp = self.client.get("/api/gamification/records/")
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]["ratio"], "2.00")
        self.assertEqual(resp.data[0]["exercise_name"], "Squat")

    def test_the_leaderboard_needs_a_login(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/gamification/leaderboard/").status_code, 401)
