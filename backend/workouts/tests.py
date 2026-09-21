from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.test import APITestCase

from core.testing import TenantAPIMixin, enrol

from accounts.models import MemberProfile, Role

from .models import (
    Exercise,
    SplitDay,
    SplitExercise,
    WorkoutLog,
    WorkoutSession,
    WorkoutSplit,
)

User = get_user_model()


class WorkoutScopingTests(TenantAPIMixin, APITestCase):
    """The workout logger and the progress endpoint must agree on whose data
    they show -- they previously didn't for staff, so the logger listed every
    member's sets while progress returned only the caller's."""

    def setUp(self):
        self.exercise = Exercise.objects.create(name="Bench Press")
        self.member = self._user("member", Role.MEMBER)
        self.other = self._user("other", Role.MEMBER)
        self.trainer = self._user("trainer", Role.TRAINER)
        self.admin = self._user("admin", Role.ADMIN)

        self.member.profile.trainer = self.trainer
        self.member.profile.save()

        for user in (self.member, self.other):
            session = WorkoutSession.objects.create(user=user)
            WorkoutLog.objects.create(
                session=session, exercise=self.exercise, set_number=1, reps=10, weight=50
            )

    def _user(self, username, role):
        user = User.objects.create_user(
            username=username, email=f"{username}@example.com", password="pass12345", role=role
        )
        MemberProfile.objects.get_or_create(user=user)
        enrol(user)
        return user

    def _progress(self, as_user, member=None):
        self.client.force_authenticate(as_user)
        params = {"exercise": self.exercise.id}
        if member:
            params["member"] = member.id
        return self.client.get("/api/workouts/sessions/progress/", params)

    def test_session_list_without_member_param_is_always_own(self):
        for user in (self.member, self.trainer, self.admin):
            self.client.force_authenticate(user)
            resp = self.client.get("/api/workouts/sessions/")
            owners = {row["user"] for row in resp.data["results"]}
            self.assertTrue(owners <= {user.id}, f"{user.username} saw other members' sessions")

    def test_member_sees_own_progress(self):
        resp = self._progress(self.member)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)

    def test_progress_point_carries_the_weight_unit(self):
        # The chart labels its axis from this, so a bare number isn't enough.
        point = self._progress(self.member).data[0]
        self.assertEqual(point["weight_unit"], "kg")
        self.assertEqual(point["max_weight"], 50)
        self.assertEqual(point["total_reps"], 10)

    def test_mixed_units_on_one_day_fold_into_a_single_point(self):
        session = WorkoutSession.objects.get(user=self.member)
        WorkoutLog.objects.create(
            session=session, exercise=self.exercise, set_number=2, reps=5, weight=200, weight_unit="lb"
        )

        data = self._progress(self.member).data
        self.assertEqual(len(data), 1, "one calendar day must plot as one point")
        # Reps sum across both units; the unit shown is the heaviest set's.
        self.assertEqual(data[0]["total_reps"], 15)
        self.assertEqual(data[0]["max_weight"], 200)
        self.assertEqual(data[0]["weight_unit"], "lb")

    def test_member_cannot_read_another_members_progress(self):
        resp = self._progress(self.member, member=self.other)
        self.assertEqual(resp.status_code, 403)

    def test_trainer_reads_assigned_member_progress_only(self):
        assigned = self._progress(self.trainer, member=self.member)
        self.assertEqual(assigned.status_code, 200)
        self.assertEqual(len(assigned.data), 1)

        unassigned = self._progress(self.trainer, member=self.other)
        self.assertEqual(unassigned.status_code, 403)

    def test_admin_reads_any_member_progress(self):
        resp = self._progress(self.admin, member=self.other)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)

    def test_trainer_can_log_for_assigned_member_only(self):
        self.client.force_authenticate(self.trainer)

        allowed = self.client.post("/api/workouts/sessions/", {"user": self.member.id, "notes": ""})
        self.assertEqual(allowed.status_code, 201)
        self.assertEqual(allowed.data["user"], self.member.id)

        denied = self.client.post("/api/workouts/sessions/", {"user": self.other.id, "notes": ""})
        self.assertEqual(denied.status_code, 403)


class SplitTests(TenantAPIMixin, APITestCase):
    """The weekly plan and the "what am I training today?" lookup."""

    def setUp(self):
        self.member = self._user("member", Role.MEMBER)
        self.other = self._user("other", Role.MEMBER)
        self.trainer = self._user("trainer", Role.TRAINER)
        self.member.profile.trainer = self.trainer
        self.member.profile.save()
        self.bench = Exercise.objects.create(name="Bench Press", muscle_group="Chest")
        self.squat = Exercise.objects.create(name="Back Squat", muscle_group="Legs")

    def _user(self, username, role):
        user = User.objects.create_user(
            username=username, email=f"{username}@example.com", password="pass12345", role=role
        )
        MemberProfile.objects.get_or_create(user=user)
        enrol(user)
        return user

    def _make_split(self, user=None, weekday=None, muscles=None):
        split = WorkoutSplit.objects.create(user=user or self.member, name="Test split")
        day = SplitDay.objects.create(
            split=split,
            # The view derives today from `timezone.localdate()`; using the
            # naive system date here made the test disagree with it either
            # side of midnight, so a long run could straddle the boundary
            # and fail on a weekday mismatch that means nothing.
            weekday=timezone.localdate().weekday() if weekday is None else weekday,
            label="Push",
            target_muscles=muscles or ["Chest", "Triceps"],
        )
        SplitExercise.objects.create(day=day, exercise=self.bench, order=1, target_sets=4)
        return split, day

    def test_days_per_week_is_derived_from_the_days_added(self):
        split = WorkoutSplit.objects.create(user=self.member)
        self.assertEqual(split.days_per_week, 0)
        for weekday in (0, 2, 4):
            SplitDay.objects.create(split=split, weekday=weekday, target_muscles=["Legs"])
        self.assertEqual(split.days_per_week, 3)

    def test_only_one_split_can_be_active(self):
        WorkoutSplit.objects.create(user=self.member, is_active=True)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                WorkoutSplit.objects.create(user=self.member, is_active=True)

    def test_creating_a_new_split_retires_the_previous_one(self):
        old = WorkoutSplit.objects.create(user=self.member, is_active=True)
        self.client.force_authenticate(self.member)
        resp = self.client.post("/api/workouts/splits/", {"name": "New plan"})
        self.assertEqual(resp.status_code, 201)
        old.refresh_from_db()
        self.assertFalse(old.is_active)

    def test_a_weekday_can_only_appear_once_in_a_split(self):
        split = WorkoutSplit.objects.create(user=self.member)
        SplitDay.objects.create(split=split, weekday=1, target_muscles=["Back"])
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SplitDay.objects.create(split=split, weekday=1, target_muscles=["Chest"])

    def test_today_returns_the_day_matching_todays_weekday(self):
        self._make_split()
        self.client.force_authenticate(self.member)
        data = self.client.get("/api/workouts/splits/today/").data

        self.assertTrue(data["has_split"])
        self.assertTrue(data["is_training_day"])
        self.assertEqual(data["day"]["label"], "Push")
        self.assertEqual(data["day"]["target_muscles"], ["Chest", "Triceps"])
        self.assertEqual(data["day"]["exercises"][0]["exercise_name"], "Bench Press")

    def test_today_reports_a_rest_day_when_no_day_matches(self):
        tomorrow = (timezone.localdate().weekday() + 1) % 7
        self._make_split(weekday=tomorrow)
        self.client.force_authenticate(self.member)
        data = self.client.get("/api/workouts/splits/today/").data

        self.assertTrue(data["has_split"])
        self.assertFalse(data["is_training_day"])
        self.assertIsNone(data["day"])

    def test_today_reports_no_split_at_all(self):
        self.client.force_authenticate(self.member)
        data = self.client.get("/api/workouts/splits/today/").data
        self.assertFalse(data["has_split"])
        self.assertFalse(data["is_training_day"])

    def test_only_the_active_split_answers_today(self):
        retired, _ = self._make_split()
        retired.is_active = False
        retired.save()

        self.client.force_authenticate(self.member)
        data = self.client.get("/api/workouts/splits/today/").data
        self.assertFalse(data["has_split"])

    def test_target_muscles_are_trimmed_and_deduplicated(self):
        split = WorkoutSplit.objects.create(user=self.member)
        self.client.force_authenticate(self.member)
        resp = self.client.post(
            "/api/workouts/split-days/",
            {"split": split.pk, "weekday": 3, "target_muscles": [" Chest ", "chest", "Triceps"]},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["target_muscles"], ["Chest", "Triceps"])

    def test_target_muscles_rejects_a_non_list(self):
        split = WorkoutSplit.objects.create(user=self.member)
        self.client.force_authenticate(self.member)
        resp = self.client.post(
            "/api/workouts/split-days/",
            {"split": split.pk, "weekday": 3, "target_muscles": "Chest"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_exercises_append_in_order(self):
        split, day = self._make_split()
        self.client.force_authenticate(self.member)
        resp = self.client.post(
            "/api/workouts/split-exercises/", {"day": day.pk, "exercise": self.squat.pk}
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["order"], 2)

    def test_a_member_cannot_read_or_edit_another_members_split(self):
        other_split, other_day = self._make_split(user=self.other)
        self.client.force_authenticate(self.member)

        listed = self.client.get("/api/workouts/splits/")
        self.assertEqual(listed.data["count"], 0)

        resp = self.client.post(
            "/api/workouts/split-days/",
            {
                "split": other_split.pk,
                # Any weekday but today's -- the other member's split already
                # occupies that one, which would fail on uniqueness (400)
                # before the ownership check could reject it (403).
                "weekday": (other_day.weekday + 1) % 7,
                "target_muscles": ["Back"],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_trainer_can_read_an_assigned_members_split(self):
        self._make_split()
        self.client.force_authenticate(self.trainer)

        allowed = self.client.get(f"/api/workouts/splits/today/?member={self.member.pk}")
        self.assertEqual(allowed.status_code, 200)
        self.assertTrue(allowed.data["is_training_day"])

        denied = self.client.get(f"/api/workouts/splits/today/?member={self.other.pk}")
        self.assertEqual(denied.status_code, 403)


class ExerciseDeleteTests(TenantAPIMixin, APITestCase):
    """PROTECT on logs and split entries: removing an exercise would erase a
    member's progress history and the plans that name it. The refusal is a
    400, not a ProtectedError escaping as a 500."""

    def setUp(self):
        # The catalogue is shared by every gym, so platform staff maintain it;
        # a gym admin is refused before a delete gets this far.
        self.staff = User.objects.create_user(
            username="ex_staff", email="ex_staff@example.com", password="pass12345", is_staff=True
        )
        self.member = User.objects.create_user(
            username="ex_member", email="ex_member@example.com", password="pass12345", role=Role.MEMBER
        )
        MemberProfile.objects.get_or_create(user=self.member)
        self.exercise = Exercise.objects.create(name="Delete-test Deadlift")
        self.client.force_authenticate(self.staff)

    def url(self):
        return f"/api/workouts/exercises/{self.exercise.id}/"

    def test_an_exercise_with_logged_sets_cannot_be_deleted(self):
        session = WorkoutSession.objects.create(user=self.member)
        log = WorkoutLog.objects.create(
            session=session, exercise=self.exercise, set_number=1, reps=5, weight=100
        )
        resp = self.client.delete(self.url())
        self.assertEqual(resp.status_code, 400)
        self.assertTrue(Exercise.objects.filter(pk=self.exercise.pk).exists())
        self.assertTrue(WorkoutLog.objects.filter(pk=log.pk, exercise=self.exercise).exists())

    def test_an_exercise_in_a_split_cannot_be_deleted(self):
        split = WorkoutSplit.objects.create(user=self.member, name="Pull day")
        day = SplitDay.objects.create(split=split, weekday=0, target_muscles=["Back"])
        entry = SplitExercise.objects.create(day=day, exercise=self.exercise, order=1, target_sets=3)
        resp = self.client.delete(self.url())
        self.assertEqual(resp.status_code, 400)
        self.assertTrue(SplitExercise.objects.filter(pk=entry.pk, exercise=self.exercise).exists())

    def test_an_unused_exercise_can_be_deleted(self):
        resp = self.client.delete(self.url())
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(Exercise.objects.filter(pk=self.exercise.pk).exists())
