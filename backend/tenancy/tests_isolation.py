"""Proof that one gym cannot see another gym's data.

This is the file Phase 2 exists for. Everything else -- the FKs, the backfill,
the scoped managers, the membership-driven permissions -- is machinery; these
are the assertions that say the machinery works.

Three kinds of test here, and they fail for different reasons:

* **Reads.** A caller with no standing at a gym gets nothing from it, including
  when they hold admin at their own gym. An admin is the dangerous case,
  because every permission class says yes to them locally.
* **Guessed ids.** Knowing a row's primary key must not help. These assert
  **404, not 403** -- a 403 confirms the row exists, which tells an attacker
  something. Absence is the honest answer to "not yours".
* **Writes.** A row created in one gym's scope must not land in another's, and
  a cross-tenant update must not reach across.

`enrol_everyone` is off throughout: the whole point is users who are *not*
members of the tenant they are calling, and the convenience enrolment in
`TenantAPIMixin` would quietly hand them the standing under test.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from accounts.models import MemberProfile, Role
from billing.models import Plan
from expenses.models import Expense, ExpenseCategory
from nutrition.models import FoodItem
from workouts.models import Exercise

from . import context
from .models import Membership, Organisation, Tenant

User = get_user_model()


def make_gym(slug):
    org = Organisation.objects.create(name=slug.title(), slug=slug)
    tenant = Tenant.objects.create(organisation=org, name=slug.title(), slug=f"{slug}-main")
    return org, tenant


def make_user(username, role=Role.MEMBER):
    user = User.objects.create_user(
        username=username, email=f"{username}@example.com", password="pass12345", role=role
    )
    if role == Role.MEMBER:
        MemberProfile.objects.get_or_create(user=user)
    return user


class TwoGyms(APITestCase):
    """Two unrelated gyms, each with its own admin and its own data."""

    def setUp(self):
        self.org_a, self.gym_a = make_gym("gym-a")
        self.org_b, self.gym_b = make_gym("gym-b")

        self.admin_a = make_user("admin_a", Role.ADMIN)
        self.admin_b = make_user("admin_b", Role.ADMIN)
        Membership.objects.create(user=self.admin_a, tenant=self.gym_a, role=Role.ADMIN)
        Membership.objects.create(user=self.admin_b, tenant=self.gym_b, role=Role.ADMIN)

        with context.scope(self.gym_a):
            self.category_a = ExpenseCategory.objects.create(name="Rent")
            self.expense_a = Expense.objects.create(
                category=self.category_a, amount=Decimal("25000"), spent_on="2026-01-05"
            )
            self.plan_a = Plan.objects.create(
                name="Monthly", price=Decimal("1500"), duration_days=30
            )

        with context.scope(self.gym_b):
            self.category_b = ExpenseCategory.objects.create(name="Rent")
            self.expense_b = Expense.objects.create(
                category=self.category_b, amount=Decimal("900"), spent_on="2026-01-05"
            )

    def as_(self, user, tenant):
        """Point the client at `tenant`, authenticated as `user`."""
        self.client.force_authenticate(user)
        return f"/api/t/{tenant.slug}"


class ScopedReadTests(TwoGyms):
    def test_the_manager_returns_only_this_gyms_rows(self):
        with context.scope(self.gym_a):
            self.assertEqual(list(Expense.objects.all()), [self.expense_a])
        with context.scope(self.gym_b):
            self.assertEqual(list(Expense.objects.all()), [self.expense_b])

    def test_unscoped_sees_both_which_is_why_it_is_named_that(self):
        self.assertEqual(Expense.unscoped.count(), 2)

    def test_a_query_with_no_tenant_in_scope_raises_rather_than_returning_everything(self):
        """Fail closed. Returning all rows here is the bug this prevents."""
        with self.assertRaises(context.TenantScopeError):
            list(Expense.objects.all())

    def test_platform_scope_still_refuses_scoped_reads(self):
        """"Deliberately no gym" is not "every gym"."""
        with context.platform_scope():
            with self.assertRaises(context.TenantScopeError):
                list(Expense.objects.all())

    def test_organisation_scoped_config_follows_the_brand(self):
        with context.scope(self.gym_a):
            self.assertEqual([c.pk for c in ExpenseCategory.objects.all()], [self.category_a.pk])


class CrossTenantApiTests(TwoGyms):
    def test_an_admin_of_another_gym_is_refused(self):
        """The dangerous case: locally they pass every permission class."""
        base = self.as_(self.admin_b, self.gym_a)
        self.assertEqual(self.client.get(f"{base}/expenses/").status_code, 403)

    def test_their_own_gym_still_works(self):
        """Otherwise the test above would pass with everything broken."""
        base = self.as_(self.admin_b, self.gym_b)
        self.assertEqual(self.client.get(f"{base}/expenses/").status_code, 200)

    def test_a_member_of_neither_gym_is_refused(self):
        stranger = make_user("stranger")
        base = self.as_(stranger, self.gym_a)
        self.assertEqual(self.client.get(f"{base}/expenses/").status_code, 403)

    def test_an_unknown_tenant_slug_is_not_a_way_in(self):
        self.client.force_authenticate(self.admin_a)
        resp = self.client.get("/api/t/no-such-gym/expenses/")
        self.assertIn(resp.status_code, (403, 404))

    def test_dropping_the_prefix_does_not_bypass_scoping(self):
        """An unprefixed call resolves no tenant, so it must not be a back door."""
        self.client.force_authenticate(self.admin_a)
        self.assertEqual(self.client.get("/api/expenses/").status_code, 403)


class GuessedIdTests(TwoGyms):
    """Knowing a primary key must not help.

    404 rather than 403 throughout: a 403 on a row that exists elsewhere
    confirms it exists, which is a small leak of its own.
    """

    def test_reading_another_gyms_row_by_id_is_a_404(self):
        base = self.as_(self.admin_b, self.gym_b)
        resp = self.client.get(f"{base}/expenses/{self.expense_a.pk}/")
        self.assertEqual(resp.status_code, 404)

    def test_the_same_id_in_its_own_gym_is_found(self):
        """Pins that the 404 above is about ownership, not a broken route."""
        base = self.as_(self.admin_a, self.gym_a)
        resp = self.client.get(f"{base}/expenses/{self.expense_a.pk}/")
        self.assertEqual(resp.status_code, 200)

    def test_updating_another_gyms_row_by_id_is_a_404(self):
        base = self.as_(self.admin_b, self.gym_b)
        resp = self.client.patch(
            f"{base}/expenses/{self.expense_a.pk}/", {"amount": "1.00"}, format="json"
        )
        self.assertEqual(resp.status_code, 404)
        self.expense_a.refresh_from_db()
        self.assertEqual(self.expense_a.amount, Decimal("25000"))

    def test_deleting_another_gyms_row_by_id_is_a_404(self):
        base = self.as_(self.admin_b, self.gym_b)
        resp = self.client.delete(f"{base}/expenses/{self.expense_a.pk}/")
        self.assertEqual(resp.status_code, 404)
        self.assertTrue(Expense.unscoped.filter(pk=self.expense_a.pk).exists())


class ScopedWriteTests(TwoGyms):
    def test_a_row_created_in_scope_belongs_to_that_gym(self):
        with context.scope(self.gym_b):
            made = Expense.objects.create(
                category=self.category_b, amount=Decimal("50"), spent_on="2026-02-01"
            )
        self.assertEqual(made.tenant_id, self.gym_b.pk)

    def test_an_explicit_tenant_is_not_overwritten(self):
        """Platform tooling writes across gyms deliberately; stamping must not
        silently redirect it."""
        with context.scope(self.gym_a):
            made = Expense.objects.create(
                category=self.category_b,
                amount=Decimal("50"),
                spent_on="2026-02-01",
                tenant=self.gym_b,
            )
        self.assertEqual(made.tenant_id, self.gym_b.pk)

    def test_a_row_written_through_the_api_lands_in_the_calling_gym(self):
        base = self.as_(self.admin_b, self.gym_b)
        resp = self.client.post(
            f"{base}/expenses/",
            {"category": self.category_b.pk, "amount": "75.00", "spent_on": "2026-02-02"},
        )
        self.assertEqual(resp.status_code, 201)
        made = Expense.unscoped.get(pk=resp.data["id"])
        self.assertEqual(made.tenant_id, self.gym_b.pk)

    def test_organisation_scoped_writes_follow_the_brand(self):
        with context.scope(self.gym_b):
            plan = Plan.objects.create(
                name="Weekly", price=Decimal("400"), duration_days=7
            )
        self.assertEqual(plan.organisation_id, self.org_b.pk)


class SharedCatalogueWriteTests(TwoGyms):
    """The exercise and food catalogues have no tenant column: every gym reads
    the same rows. A gym's admin passes every permission class at their own
    gym, so without a stricter rule their edit lands in every other gym's
    workout logs and diet plan totals.

    Only platform staff -- `is_staff`, the flag that already gates Django's
    /admin/ -- maintain them. Each refusal checks what gym B sees before the
    status code, so a regression reads as the cross-gym change it is.
    """

    def setUp(self):
        super().setUp()
        self.exercise = Exercise.objects.create(name="Shared Bench Press")
        self.food = FoodItem.objects.create(name="Shared Oats", calories=Decimal("389"))

    def test_an_admin_of_one_gym_cannot_rename_a_shared_exercise(self):
        base = self.as_(self.admin_a, self.gym_a)
        resp = self.client.patch(
            f"{base}/workouts/exercises/{self.exercise.pk}/",
            {"name": "Renamed by gym A"},
            format="json",
        )

        base = self.as_(self.admin_b, self.gym_b)
        seen_by_b = [row["name"] for row in self.client.get(f"{base}/workouts/exercises/").data]
        self.assertIn("Shared Bench Press", seen_by_b)
        self.assertEqual(resp.status_code, 403)

    def test_an_admin_of_one_gym_cannot_change_a_shared_foods_macros(self):
        base = self.as_(self.admin_a, self.gym_a)
        resp = self.client.patch(
            f"{base}/nutrition/foods/{self.food.pk}/", {"calories": "1"}, format="json"
        )

        base = self.as_(self.admin_b, self.gym_b)
        seen_by_b = self.client.get(f"{base}/nutrition/foods/{self.food.pk}/").data
        self.assertEqual(Decimal(seen_by_b["calories"]), Decimal("389"))
        self.assertEqual(resp.status_code, 403)

    def test_an_admin_of_one_gym_cannot_delete_shared_entries(self):
        base = self.as_(self.admin_a, self.gym_a)
        exercise_resp = self.client.delete(f"{base}/workouts/exercises/{self.exercise.pk}/")
        food_resp = self.client.delete(f"{base}/nutrition/foods/{self.food.pk}/")

        base = self.as_(self.admin_b, self.gym_b)
        exercises_b = [row["id"] for row in self.client.get(f"{base}/workouts/exercises/").data]
        foods_b = [row["id"] for row in self.client.get(f"{base}/nutrition/foods/").data]
        self.assertIn(self.exercise.pk, exercises_b)
        self.assertIn(self.food.pk, foods_b)
        self.assertEqual(exercise_resp.status_code, 403)
        self.assertEqual(food_resp.status_code, 403)

    def test_an_admin_of_one_gym_cannot_add_to_the_shared_catalogues(self):
        base = self.as_(self.admin_a, self.gym_a)
        exercise_resp = self.client.post(f"{base}/workouts/exercises/", {"name": "Gym A special"})
        food_resp = self.client.post(
            f"{base}/nutrition/foods/", {"name": "Gym A shake", "calories": "200"}
        )

        self.assertFalse(Exercise.objects.filter(name="Gym A special").exists())
        self.assertFalse(FoodItem.objects.filter(name="Gym A shake").exists())
        self.assertEqual(exercise_resp.status_code, 403)
        self.assertEqual(food_resp.status_code, 403)

    def test_platform_staff_still_maintain_the_catalogues(self):
        """Otherwise the refusals above would pass with writes broken for
        everyone. Staff need no membership at the gym in the URL: the rows
        belong to the platform, not to that gym."""
        staff = make_user("catalogue_staff")
        staff.is_staff = True
        staff.save()

        base = self.as_(staff, self.gym_a)
        resp = self.client.patch(
            f"{base}/workouts/exercises/{self.exercise.pk}/",
            {"name": "Flat Bench Press"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.exercise.refresh_from_db()
        self.assertEqual(self.exercise.name, "Flat Bench Press")

    def test_every_gym_still_reads_the_catalogues(self):
        for admin, gym in ((self.admin_a, self.gym_a), (self.admin_b, self.gym_b)):
            base = self.as_(admin, gym)
            with self.subTest(gym=gym.slug):
                self.assertEqual(self.client.get(f"{base}/workouts/exercises/").status_code, 200)
                self.assertEqual(self.client.get(f"{base}/nutrition/foods/").status_code, 200)


class ModelRegistryTests(APITestCase):
    """Every tenant-owned model actually uses a scoped manager.

    The one test that keeps this true as the codebase grows. Scoping applied
    model-by-model rots the moment somebody adds the forty-sixth: it works, it
    is reviewed, and it quietly returns every gym's rows. Walking the registry
    means a new model is either scoped or listed below with a reason.
    """

    #: Models with no tenant column, and why that is correct.
    PLATFORM_OWNED = {
        # Who a person is, across every gym they belong to.
        "accounts.User",
        "accounts.MemberProfile",
        # How that person signs in, which covers every gym they belong to.
        "accounts.MfaDevice",
        "accounts.MfaRecoveryCode",
        "tenancy.Organisation",
        "tenancy.Tenant",
        "tenancy.Membership",
        # Shared catalogues. A per-gym addition carries a nullable FK instead.
        "workouts.Exercise",
        "workouts.ExerciseVideo",
        "nutrition.FoodItem",
        # Children reached only through a scoped parent.
        "workouts.WorkoutSplit",
        "workouts.SplitDay",
        "workouts.SplitExercise",
        "nutrition.DietMealItem",
        "gamification.GamificationProfile",
        # Hangs off a Referral, which is scoped; there is no way to reach one
        # without going through its parent first.
        "referrals.ReferralReward",
    }

    def test_every_model_is_either_scoped_or_explicitly_exempt(self):
        from django.apps import apps

        ours = {"accounts", "attendance", "billing", "bodystats", "branding",
                "commissions", "crm", "devices", "expenses", "feedback",
                "gallery", "gamification", "instructors", "invoicing",
                "messaging", "notifications", "nutrition", "pt", "referrals",
                "reports", "schedule_app", "shifts", "tenancy",
                "workouts"}

        unscoped = []
        for model in apps.get_models():
            label = f"{model._meta.app_label}.{model.__name__}"
            if model._meta.app_label not in ours or label in self.PLATFORM_OWNED:
                continue
            if getattr(model, "tenant_field", None) is None:
                unscoped.append(label)

        self.assertEqual(
            unscoped,
            [],
            "These models carry no tenant scoping. Add a tenant_field and the "
            "scoped managers, or add them to PLATFORM_OWNED with a reason:\n  "
            + "\n  ".join(unscoped),
        )
