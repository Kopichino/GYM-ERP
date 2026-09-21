from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.utils import IntegrityError
from django.utils import timezone
from rest_framework.test import APITestCase

from core.testing import TenantAPIMixin, enrol

from accounts.models import MemberProfile, Role

from . import macros
from .models import DietDay, DietMeal, DietMealItem, DietPlan, FoodCategory, FoodItem

User = get_user_model()


def make_food(name, calories, protein=0, carbs=0, fat=0):
    return FoodItem.objects.create(
        name=name,
        category=FoodCategory.OTHER,
        calories=Decimal(calories),
        protein_g=Decimal(protein),
        carbs_g=Decimal(carbs),
        fat_g=Decimal(fat),
    )


class MacroDerivationTests(TenantAPIMixin, APITestCase):
    """Totals are computed, never stored -- these tests prove the numbers move
    when the catalogue does."""

    def setUp(self):
        self.member = User.objects.create_user(
            username="eater", email="e@example.com", password="pass12345"
        )
        self.chicken = make_food("Chicken", 165, protein=31)
        self.rice = make_food("Rice", 130, protein=2.7, carbs=28)

        self.plan = DietPlan.objects.create(user=self.member, name="Test plan")
        self.day = DietDay.objects.create(plan=self.plan, weekday=0)
        self.meal = DietMeal.objects.create(day=self.day, meal_type="lunch")
        DietMealItem.objects.create(meal=self.meal, food=self.chicken, quantity_g=Decimal("200"))
        DietMealItem.objects.create(meal=self.meal, food=self.rice, quantity_g=Decimal("150"))

    def test_portion_scales_from_per_100g(self):
        result = macros.for_portion(self.chicken, Decimal("200"))
        self.assertEqual(result["calories"], Decimal("330.0"))
        self.assertEqual(result["protein_g"], Decimal("62.0"))

    def test_meal_total_sums_its_portions(self):
        result = macros.for_meal(self.meal)
        # 330 kcal chicken + 195 kcal rice
        self.assertEqual(result["calories"], Decimal("525.0"))
        self.assertEqual(result["protein_g"], Decimal("66.1"))

    def test_correcting_a_food_moves_every_plan_using_it(self):
        before = macros.for_day(self.day)["calories"]
        self.chicken.calories = Decimal("200")
        self.chicken.save(update_fields=["calories"])
        self.day.refresh_from_db()
        after = macros.for_day(self.day)["calories"]
        self.assertNotEqual(before, after)
        self.assertEqual(after, Decimal("595.0"))

    def test_plan_reports_a_daily_average_not_a_weekly_sum(self):
        second = DietDay.objects.create(plan=self.plan, weekday=1)
        meal = DietMeal.objects.create(day=second, meal_type="dinner")
        DietMealItem.objects.create(meal=meal, food=self.rice, quantity_g=Decimal("100"))
        self.plan.refresh_from_db()
        # (525 + 130) / 2 days
        self.assertEqual(macros.for_plan(self.plan)["calories"], Decimal("327.5"))

    def test_empty_plan_reports_zeroes_rather_than_dividing_by_zero(self):
        empty_plan = DietPlan.objects.create(user=self.member, name="Nothing yet", is_active=False)
        self.assertEqual(macros.for_plan(empty_plan)["calories"], Decimal("0.0"))


class DietPlanApiTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.member = User.objects.create_user(
            username="dietmember", email="dm@example.com", password="pass12345"
        )
        self.other = User.objects.create_user(
            username="stranger", email="s@example.com", password="pass12345"
        )
        self.trainer = User.objects.create_user(
            username="dietcoach", email="dc@example.com", password="pass12345", role=Role.TRAINER
        )
        # `create_user` makes no profile -- one is created on the signup path,
        # so the roster link has to be set up explicitly here.
        MemberProfile.objects.update_or_create(
            user=self.member, defaults={"trainer": self.trainer}
        )
        MemberProfile.objects.get_or_create(user=self.other)
        for person in (self.member, self.other, self.trainer):
            enrol(person)
        self.food = make_food("Oats", 389, protein=16.9, carbs=66)
        self.client.force_authenticate(self.member)

    def test_member_builds_a_plan_and_sees_derived_totals(self):
        plan = self.client.post("/api/nutrition/plans/", {"name": "Cutting"}).data
        day = self.client.post(
            "/api/nutrition/days/", {"plan": plan["id"], "weekday": 0, "label": "Training day"}
        ).data
        meal = self.client.post(
            "/api/nutrition/meals/", {"day": day["id"], "meal_type": "breakfast"}
        ).data
        self.client.post(
            "/api/nutrition/items/",
            {"meal": meal["id"], "food": self.food.id, "quantity_g": "100"},
        )

        resp = self.client.get(f"/api/nutrition/plans/{plan['id']}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["days_planned"], 1)
        self.assertEqual(Decimal(resp.data["daily_macros"]["calories"]), Decimal("389.0"))

    def test_creating_a_plan_retires_the_previous_one(self):
        first = self.client.post("/api/nutrition/plans/", {"name": "Old"}).data
        second = self.client.post("/api/nutrition/plans/", {"name": "New"}).data
        self.assertFalse(DietPlan.objects.get(pk=first["id"]).is_active)
        self.assertTrue(DietPlan.objects.get(pk=second["id"]).is_active)

    def test_activate_switches_back_without_breaking_the_one_active_rule(self):
        first = self.client.post("/api/nutrition/plans/", {"name": "Old"}).data
        self.client.post("/api/nutrition/plans/", {"name": "New"})
        resp = self.client.post(f"/api/nutrition/plans/{first['id']}/activate/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(DietPlan.objects.filter(user=self.member, is_active=True).count(), 1)

    def test_two_active_plans_are_impossible_at_the_database_level(self):
        DietPlan.objects.create(user=self.member, name="One", is_active=True)
        with self.assertRaises(IntegrityError):
            DietPlan.objects.create(user=self.member, name="Two", is_active=True)

    def test_is_active_cannot_be_set_from_the_request_body(self):
        """A form post that omits the field must not file the new plan away."""
        plan = self.client.post("/api/nutrition/plans/", {"name": "X", "is_active": False}).data
        self.assertTrue(DietPlan.objects.get(pk=plan["id"]).is_active)

    def test_member_cannot_read_another_members_plan(self):
        DietPlan.objects.create(user=self.other, name="Not yours")
        resp = self.client.get("/api/nutrition/plans/")
        self.assertEqual(resp.data["count"], 0)

    def test_member_cannot_target_another_member(self):
        resp = self.client.get(f"/api/nutrition/plans/?member={self.other.id}")
        self.assertEqual(resp.status_code, 403)

    def test_trainer_can_write_a_plan_for_their_own_member(self):
        self.client.force_authenticate(self.trainer)
        resp = self.client.post(
            f"/api/nutrition/plans/?member={self.member.id}", {"name": "Coach's plan"}
        )
        self.assertEqual(resp.status_code, 201)
        plan = DietPlan.objects.get(pk=resp.data["id"])
        self.assertEqual(plan.user, self.member)
        self.assertEqual(plan.created_by, self.trainer)

    def test_trainer_cannot_write_for_someone_elses_member(self):
        self.client.force_authenticate(self.trainer)
        resp = self.client.post(
            f"/api/nutrition/plans/?member={self.other.id}", {"name": "Nope"}
        )
        self.assertEqual(resp.status_code, 403)

    def test_today_answers_for_the_current_weekday(self):
        plan = self.client.post("/api/nutrition/plans/", {"name": "Weekly"}).data
        today = timezone.localdate().weekday()
        self.client.post(
            "/api/nutrition/days/", {"plan": plan["id"], "weekday": today, "label": "High carb"}
        )
        resp = self.client.get("/api/nutrition/plans/today/")
        self.assertTrue(resp.data["has_plan"])
        self.assertTrue(resp.data["is_planned_day"])
        self.assertEqual(resp.data["day"]["label"], "High carb")

    def test_today_is_honest_when_nothing_is_planned(self):
        resp = self.client.get("/api/nutrition/plans/today/")
        self.assertFalse(resp.data["has_plan"])
        self.assertFalse(resp.data["is_planned_day"])
        self.assertIsNone(resp.data["day"])

    def test_items_cannot_be_added_to_someone_elses_meal(self):
        other_plan = DietPlan.objects.create(user=self.other, name="Theirs")
        other_day = DietDay.objects.create(plan=other_plan, weekday=0)
        other_meal = DietMeal.objects.create(day=other_day, meal_type="lunch")
        resp = self.client.post(
            "/api/nutrition/items/",
            {"meal": other_meal.id, "food": self.food.id, "quantity_g": "50"},
        )
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(DietMealItem.objects.filter(meal=other_meal).exists())


class FoodCatalogueTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.member = User.objects.create_user(
            username="browser", email="b@example.com", password="pass12345"
        )
        self.admin = User.objects.create_user(
            username="foodadmin", email="fa@example.com", password="pass12345", role=Role.ADMIN
        )
        make_food("Banana", 89)

    def test_members_can_read_the_catalogue(self):
        self.client.force_authenticate(self.member)
        resp = self.client.get("/api/nutrition/foods/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)

    def test_the_catalogue_is_not_paginated(self):
        """The food picker offers the whole list; a page of 20 hid most of it."""
        for n in range(25):
            make_food(f"Filler {n}", 100)
        self.client.force_authenticate(self.member)
        resp = self.client.get("/api/nutrition/foods/")
        self.assertEqual(len(resp.data), 26)

    def test_members_cannot_edit_the_catalogue(self):
        """One member's typo must not skew every plan referencing that food."""
        self.client.force_authenticate(self.member)
        resp = self.client.post(
            "/api/nutrition/foods/", {"name": "Cake", "calories": "1"}
        )
        self.assertEqual(resp.status_code, 403)

    def _staff(self):
        # The catalogue is shared by every gym on the platform, so maintaining
        # it is platform staff's job rather than any one gym's admin.
        return User.objects.get_or_create(
            username="catalogue_staff", defaults={"email": "cs@example.com", "is_staff": True}
        )[0]

    def test_platform_staff_can_add_a_food(self):
        self.client.force_authenticate(self._staff())
        resp = self.client.post(
            "/api/nutrition/foods/",
            {"name": "Idli", "calories": "132", "protein_g": "3", "carbs_g": "28", "fat_g": "0.5"},
        )
        self.assertEqual(resp.status_code, 201)

    def test_a_gym_admin_cannot_edit_the_shared_catalogue(self):
        """Every gym reads these rows, so one gym's admin changing a food's
        macros would change every other gym's diet plan totals."""
        banana = FoodItem.objects.get(name="Banana")
        self.client.force_authenticate(self.admin)
        self.assertEqual(
            self.client.post("/api/nutrition/foods/", {"name": "Idli", "calories": "132"}).status_code,
            403,
        )
        self.assertEqual(
            self.client.patch(f"/api/nutrition/foods/{banana.id}/", {"calories": "1"}).status_code,
            403,
        )
        self.assertEqual(self.client.delete(f"/api/nutrition/foods/{banana.id}/").status_code, 403)
        banana.refresh_from_db()
        self.assertEqual(banana.calories, Decimal("89"))

    def test_search_narrows_the_list(self):
        make_food("Brown rice", 123)
        self.client.force_authenticate(self.member)
        resp = self.client.get("/api/nutrition/foods/?search=rice")
        self.assertEqual(len(resp.data), 1)

    def test_inactive_foods_are_hidden_from_members(self):
        FoodItem.objects.update(is_active=False)
        self.client.force_authenticate(self.member)
        self.assertEqual(len(self.client.get("/api/nutrition/foods/").data), 0)
        self.client.force_authenticate(self.admin)
        self.assertEqual(len(self.client.get("/api/nutrition/foods/").data), 1)

    def test_a_food_in_a_diet_plan_cannot_be_deleted(self):
        """PROTECT on the meal item: pulling a food would silently change the
        macros of every plan that uses it. The refusal is a 400, not a 500."""
        food = FoodItem.objects.get(name="Banana")
        plan = DietPlan.objects.create(user=self.member, name="Bulk")
        day = DietDay.objects.create(plan=plan, weekday=0)
        meal = DietMeal.objects.create(day=day, meal_type="breakfast")
        item = DietMealItem.objects.create(meal=meal, food=food, quantity_g=Decimal("120"))

        self.client.force_authenticate(self._staff())
        resp = self.client.delete(f"/api/nutrition/foods/{food.id}/")

        self.assertEqual(resp.status_code, 400)
        self.assertTrue(FoodItem.objects.filter(pk=food.pk).exists())
        self.assertTrue(DietMealItem.objects.filter(pk=item.pk, food=food).exists())

    def test_an_unused_food_can_be_deleted(self):
        food = make_food("Retired snack", 100)
        self.client.force_authenticate(self._staff())
        resp = self.client.delete(f"/api/nutrition/foods/{food.id}/")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(FoodItem.objects.filter(pk=food.pk).exists())
