from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from core.testing import TenantAPIMixin, enrol

from accounts.models import MemberProfile, Role

from .models import BodyMeasurement, GoalStatus, GoalType, MemberGoal
from .services import bmi_category, calculate_bmi, goal_progress

User = get_user_model()


def make_user(username, role=Role.MEMBER, height_cm=None):
    user = User.objects.create_user(
        username=username, email=f"{username}@example.com", password="pass12345", role=role
    )
    MemberProfile.objects.update_or_create(user=user, defaults={"height_cm": height_cm})
    enrol(user)
    user.refresh_from_db()
    return user


class BmiTests(TenantAPIMixin, APITestCase):
    def test_bmi_is_weight_over_height_squared(self):
        # 80kg at 180cm -> 80 / 1.8^2 = 24.7
        self.assertEqual(calculate_bmi(Decimal("80"), 180), Decimal("24.7"))

    def test_bmi_needs_both_inputs(self):
        self.assertIsNone(calculate_bmi(Decimal("80"), None))
        self.assertIsNone(calculate_bmi(None, 180))

    def test_who_bands(self):
        self.assertEqual(bmi_category(Decimal("17.0")), "underweight")
        self.assertEqual(bmi_category(Decimal("22.0")), "normal")
        self.assertEqual(bmi_category(Decimal("27.0")), "overweight")
        self.assertEqual(bmi_category(Decimal("31.0")), "obese")
        # Boundaries land in the higher band, per WHO.
        self.assertEqual(bmi_category(Decimal("25.0")), "overweight")
        self.assertEqual(bmi_category(Decimal("18.5")), "normal")


class GoalProgressTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.member = make_user("member", height_cm=180)

    def _weigh(self, kg, days_ago=0):
        return BodyMeasurement.objects.create(
            user=self.member,
            weight_kg=Decimal(str(kg)),
            recorded_on=date.today() - timedelta(days=days_ago),
        )

    def test_weight_loss_goal_counts_down(self):
        self._weigh(85, days_ago=10)
        self._weigh(80)
        goal = MemberGoal.objects.create(
            user=self.member,
            goal_type=GoalType.WEIGHT,
            start_value=Decimal("90"),
            target_value=Decimal("80"),
        )
        # 90 -> 80 target, now at 80: the whole distance is covered.
        self.assertEqual(goal_progress(goal), Decimal("100.00"))

    def test_weight_gain_goal_counts_up(self):
        self._weigh(65)
        goal = MemberGoal.objects.create(
            user=self.member,
            goal_type=GoalType.WEIGHT,
            start_value=Decimal("60"),
            target_value=Decimal("70"),
        )
        # 60 -> 70 target, now at 65: halfway.
        self.assertEqual(goal_progress(goal), Decimal("50.00"))

    def test_progress_is_clamped_past_the_target(self):
        self._weigh(55)
        goal = MemberGoal.objects.create(
            user=self.member,
            goal_type=GoalType.WEIGHT,
            start_value=Decimal("80"),
            target_value=Decimal("70"),
        )
        self.assertEqual(goal_progress(goal), Decimal("100.00"))

    def test_progress_is_none_without_any_measurement(self):
        goal = MemberGoal.objects.create(
            user=self.member, goal_type=GoalType.WEIGHT, target_value=Decimal("70")
        )
        self.assertIsNone(goal_progress(goal))

    def test_attendance_goal_counts_this_months_visits(self):
        self.member.check_ins.create()
        goal = MemberGoal.objects.create(
            user=self.member,
            goal_type=GoalType.ATTENDANCE,
            start_value=Decimal("0"),
            target_value=Decimal("10"),
        )
        self.assertEqual(goal_progress(goal), Decimal("10.00"))

    def test_goal_flips_to_achieved_once_reached(self):
        goal = MemberGoal.objects.create(
            user=self.member,
            goal_type=GoalType.WEIGHT,
            start_value=Decimal("90"),
            target_value=Decimal("80"),
        )
        self.client.force_authenticate(self.member)
        self.client.post(
            "/api/bodystats/measurements/", {"weight_kg": "79.5", "recorded_on": str(date.today())}
        )
        goal.refresh_from_db()
        self.assertEqual(goal.status, GoalStatus.ACHIEVED)


class BodyStatsApiTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.member = make_user("member", height_cm=175)
        self.other = make_user("other", height_cm=175)
        self.trainer = make_user("trainer", Role.TRAINER)
        self.admin = make_user("admin", Role.ADMIN)
        self.member.profile.trainer = self.trainer
        self.member.profile.save()

    def test_member_records_and_reads_own_measurement(self):
        self.client.force_authenticate(self.member)
        resp = self.client.post("/api/bodystats/measurements/", {"weight_kg": "72.5"})
        self.assertEqual(resp.status_code, 201)
        # 72.5kg at 175cm -> 23.7
        self.assertEqual(str(resp.data["bmi"]), "23.7")

    def test_same_day_reweigh_updates_instead_of_duplicating(self):
        self.client.force_authenticate(self.member)
        today = str(date.today())
        self.client.post("/api/bodystats/measurements/", {"weight_kg": "72.5", "recorded_on": today})
        resp = self.client.post(
            "/api/bodystats/measurements/", {"weight_kg": "73.0", "recorded_on": today}
        )
        self.assertIn(resp.status_code, (200, 201))
        self.assertEqual(BodyMeasurement.objects.filter(user=self.member).count(), 1)
        self.assertEqual(BodyMeasurement.objects.get(user=self.member).weight_kg, Decimal("73.00"))

    def test_measurements_are_scoped_to_the_caller(self):
        BodyMeasurement.objects.create(user=self.other, weight_kg=Decimal("90"))
        self.client.force_authenticate(self.member)
        resp = self.client.get("/api/bodystats/measurements/")
        self.assertEqual(resp.data["count"], 0)

    def test_member_cannot_read_another_members_stats(self):
        self.client.force_authenticate(self.member)
        resp = self.client.get(f"/api/bodystats/summary/?member={self.other.id}")
        self.assertEqual(resp.status_code, 403)

    def test_trainer_reads_assigned_member_but_not_others(self):
        BodyMeasurement.objects.create(user=self.member, weight_kg=Decimal("72"))
        self.client.force_authenticate(self.trainer)

        assigned = self.client.get(f"/api/bodystats/summary/?member={self.member.id}")
        self.assertEqual(assigned.status_code, 200)
        self.assertEqual(str(assigned.data["weight_kg"]), "72.00")

        unassigned = self.client.get(f"/api/bodystats/summary/?member={self.other.id}")
        self.assertEqual(unassigned.status_code, 403)

    def test_trainer_can_weigh_in_an_assigned_member(self):
        self.client.force_authenticate(self.trainer)
        resp = self.client.post(
            "/api/bodystats/measurements/", {"weight_kg": "71.0", "user": self.member.id}
        )
        self.assertEqual(resp.status_code, 201)
        measurement = BodyMeasurement.objects.get(user=self.member)
        self.assertEqual(measurement.recorded_by, self.trainer)

    def test_trainer_cannot_weigh_in_an_unassigned_member(self):
        self.client.force_authenticate(self.trainer)
        resp = self.client.post(
            "/api/bodystats/measurements/", {"weight_kg": "71.0", "user": self.other.id}
        )
        self.assertEqual(resp.status_code, 403)

    def test_summary_reports_bmi_band_and_movement(self):
        BodyMeasurement.objects.create(
            user=self.member, weight_kg=Decimal("80"), recorded_on=date.today() - timedelta(days=7)
        )
        BodyMeasurement.objects.create(user=self.member, weight_kg=Decimal("78"))
        self.client.force_authenticate(self.member)
        data = self.client.get("/api/bodystats/summary/").data

        self.assertEqual(str(data["bmi"]), "25.5")
        self.assertEqual(data["bmi_category"], "overweight")
        self.assertEqual(str(data["change_since_previous"]), "-2.00")
        self.assertEqual(data["measurement_count"], 2)

    def test_custom_goal_requires_a_title(self):
        self.client.force_authenticate(self.member)
        resp = self.client.post(
            "/api/bodystats/goals/", {"goal_type": "custom", "target_value": "5"}
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("title", resp.data)


class ProfileHeightTests(TenantAPIMixin, APITestCase):
    """Height moved onto MemberProfile, which also made /me/ writable."""

    def setUp(self):
        self.member = make_user("member")

    def test_member_sets_own_height_via_me(self):
        self.client.force_authenticate(self.member)
        resp = self.client.patch("/api/auth/me/", {"profile": {"height_cm": 178}}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.member.profile.refresh_from_db()
        self.assertEqual(self.member.profile.height_cm, 178)

    def test_member_cannot_promote_themselves_or_set_status_via_me(self):
        self.client.force_authenticate(self.member)
        self.client.patch(
            "/api/auth/me/",
            {"role": "admin", "profile": {"membership_status": "active", "height_cm": 170}},
            format="json",
        )
        self.member.refresh_from_db()
        self.member.profile.refresh_from_db()
        self.assertEqual(self.member.role, Role.MEMBER)
        self.assertFalse(self.member.is_staff)
        # The writable field still applied; the protected one was ignored.
        self.assertEqual(self.member.profile.height_cm, 170)


class ExistingInvariantsTests(TenantAPIMixin, APITestCase):
    """Guards on the two rules this feature was not allowed to disturb."""

    def setUp(self):
        self.member = make_user("member")

    def test_one_open_check_in_per_user_still_enforced(self):
        self.client.force_authenticate(self.member)
        first = self.client.post("/api/attendance/check_in/")
        second = self.client.post("/api/attendance/check_in/")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 400)
        self.assertEqual(self.member.check_ins.filter(check_out_time__isnull=True).count(), 1)

    def test_membership_status_is_still_derived_not_writable(self):
        from billing.models import Plan
        from billing.services import record_payment

        plan = Plan.objects.create(name="Monthly", price=Decimal("1000"), duration_days=30)
        record_payment(
            member=self.member, plan=plan, amount=Decimal("1000"), method="cash", recorded_by=None
        )
        self.member.profile.refresh_from_db()
        self.assertEqual(self.member.profile.membership_status, "active")

        # Writing it directly through the member's own endpoint must not stick.
        self.client.force_authenticate(self.member)
        self.client.patch(
            "/api/auth/me/", {"profile": {"membership_status": "expired"}}, format="json"
        )
        self.member.profile.refresh_from_db()
        self.assertEqual(self.member.profile.membership_status, "active")
