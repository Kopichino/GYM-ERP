"""Inside one gym: whose rows a caller may touch, and which fields they may set.

Two shapes of hole, both found in this pass:

* **Re-parenting.** A child row (a logged set, a training day, a meal) was
  checked against its *current* parent on update, while the new parent named in
  the body was never checked -- so a member could move their own row into
  somebody else's plan or session.
* **Mass assignment.** Serializers that accepted fields the caller has no say
  over: a member marking their own PT session paid, or naming its price.

The pins at the bottom are protections that already held; they are here so a
future serializer change cannot quietly undo them.
"""

import tempfile
from datetime import timedelta
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone

from accounts.models import MemberProfile, Role
from attendance.models import CheckInOut
from billing.models import PaymentMethod, Plan
from billing.services import record_payment
from bodystats.models import BodyMeasurement
from core.testing import founding_tenant
from expenses.models import Expense, ExpenseCategory
from gallery.models import GalleryPost
from invoicing.services import issue_invoice
from nutrition.models import DietDay, DietMeal, DietMealItem, DietPlan, FoodItem
from pt.models import Availability, PTSession
from referrals.models import Referral
from tenancy.models import Membership
from workouts.models import (
    Exercise,
    SplitDay,
    SplitExercise,
    WorkoutLog,
    WorkoutSession,
    WorkoutSplit,
)

from .testing import OneGymTestCase, png_bytes

TEMP_MEDIA = tempfile.mkdtemp(prefix="ironcore-objects-")


class WorkoutOwnershipTests(OneGymTestCase):
    def setUp(self):
        super().setUp()
        self.me = self.person("me")
        self.victim = self.person("victim")
        self.exercise = Exercise.objects.create(name="Back Squat")
        self.my_session = WorkoutSession.objects.create(user=self.me)
        self.victim_session = WorkoutSession.objects.create(user=self.victim)
        self.client.force_authenticate(self.me)

    def log(self, session):
        return self.client.post(
            "/api/workouts/logs/",
            {
                "session": session.pk,
                "exercise": self.exercise.pk,
                "set_number": 1,
                "reps": 8,
                "weight": "60",
            },
        )

    def test_logging_a_set_to_your_own_session_works(self):
        """The ownership check itself crashed (NameError) on every set logged."""
        resp = self.log(self.my_session)
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertTrue(WorkoutLog.objects.filter(session=self.my_session, reps=8).exists())

    def test_logging_a_set_into_someone_elses_session_is_refused(self):
        resp = self.log(self.victim_session)
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(WorkoutLog.objects.filter(session=self.victim_session).exists())

    def test_a_logged_set_cannot_be_moved_into_someone_elses_session(self):
        entry = WorkoutLog.objects.create(
            session=self.my_session, exercise=self.exercise, set_number=1, reps=5
        )
        self.client.patch(
            f"/api/workouts/logs/{entry.pk}/", {"session": self.victim_session.pk}, format="json"
        )
        entry.refresh_from_db()
        self.assertEqual(entry.session_id, self.my_session.pk)

    def test_a_session_cannot_be_handed_to_another_member(self):
        self.client.patch(
            f"/api/workouts/sessions/{self.my_session.pk}/", {"user": self.victim.pk}, format="json"
        )
        self.my_session.refresh_from_db()
        self.assertEqual(self.my_session.user_id, self.me.pk)


class SplitOwnershipTests(OneGymTestCase):
    def setUp(self):
        super().setUp()
        self.me = self.person("me")
        self.victim = self.person("victim")
        exercise = Exercise.objects.create(name="Deadlift")
        self.my_split = WorkoutSplit.objects.create(user=self.me)
        self.victim_split = WorkoutSplit.objects.create(user=self.victim)
        self.my_day = SplitDay.objects.create(split=self.my_split, weekday=1)
        self.victim_day = SplitDay.objects.create(split=self.victim_split, weekday=0)
        self.my_entry = SplitExercise.objects.create(day=self.my_day, exercise=exercise, order=1)
        self.client.force_authenticate(self.me)

    def test_a_training_day_cannot_be_moved_into_someone_elses_split(self):
        self.client.patch(
            f"/api/workouts/split-days/{self.my_day.pk}/",
            {"split": self.victim_split.pk},
            format="json",
        )
        self.my_day.refresh_from_db()
        self.assertEqual(self.my_day.split_id, self.my_split.pk)

    def test_an_exercise_cannot_be_moved_into_someone_elses_day(self):
        self.client.patch(
            f"/api/workouts/split-exercises/{self.my_entry.pk}/",
            {"day": self.victim_day.pk},
            format="json",
        )
        self.my_entry.refresh_from_db()
        self.assertEqual(self.my_entry.day_id, self.my_day.pk)


class DietOwnershipTests(OneGymTestCase):
    def setUp(self):
        super().setUp()
        self.me = self.person("me")
        self.victim = self.person("victim")
        food = FoodItem.objects.create(
            name="Paneer",
            category="protein",
            calories=Decimal("265"),
            serving_label="100 g",
            serving_grams=Decimal("100"),
        )
        self.my_plan = DietPlan.objects.create(user=self.me)
        self.victim_plan = DietPlan.objects.create(user=self.victim)
        self.my_day = DietDay.objects.create(plan=self.my_plan, weekday=1)
        self.victim_day = DietDay.objects.create(plan=self.victim_plan, weekday=0)
        self.my_meal = DietMeal.objects.create(day=self.my_day, meal_type="lunch")
        self.victim_meal = DietMeal.objects.create(day=self.victim_day, meal_type="dinner")
        self.my_item = DietMealItem.objects.create(
            meal=self.my_meal, food=food, quantity_g=Decimal("100")
        )
        self.client.force_authenticate(self.me)

    def test_a_diet_day_cannot_be_moved_into_someone_elses_plan(self):
        self.client.patch(
            f"/api/nutrition/days/{self.my_day.pk}/", {"plan": self.victim_plan.pk}, format="json"
        )
        self.my_day.refresh_from_db()
        self.assertEqual(self.my_day.plan_id, self.my_plan.pk)

    def test_a_meal_cannot_be_moved_into_someone_elses_day(self):
        self.client.patch(
            f"/api/nutrition/meals/{self.my_meal.pk}/", {"day": self.victim_day.pk}, format="json"
        )
        self.my_meal.refresh_from_db()
        self.assertEqual(self.my_meal.day_id, self.my_day.pk)

    def test_a_food_cannot_be_moved_into_someone_elses_meal(self):
        self.client.patch(
            f"/api/nutrition/items/{self.my_item.pk}/", {"meal": self.victim_meal.pk}, format="json"
        )
        self.my_item.refresh_from_db()
        self.assertEqual(self.my_item.meal_id, self.my_meal.pk)


class PersonalTrainingTamperingTests(OneGymTestCase):
    def setUp(self):
        super().setUp()
        self.trainer = self.person("coach", Role.TRAINER)
        self.me = self.person("me")
        self.tomorrow = timezone.localdate() + timedelta(days=1)
        Availability.objects.create(
            trainer=self.trainer,
            weekday=self.tomorrow.weekday(),
            start_time="06:00",
            end_time="10:00",
        )
        self.session = PTSession.objects.create(
            trainer=self.trainer,
            member=self.me,
            date=self.tomorrow,
            start_time="06:00",
            end_time="07:00",
            price=Decimal("800"),
        )

    def test_a_member_cannot_mark_their_session_paid_or_reprice_it(self):
        self.client.force_authenticate(self.me)
        self.client.patch(
            f"/api/pt/sessions/{self.session.pk}/", {"is_paid": True, "price": "0"}, format="json"
        )
        self.session.refresh_from_db()
        self.assertFalse(self.session.is_paid)
        self.assertEqual(self.session.price, Decimal("800"))

    def test_a_member_cannot_move_a_booking_by_editing_it(self):
        self.client.force_authenticate(self.me)
        self.client.patch(
            f"/api/pt/sessions/{self.session.pk}/",
            {"start_time": "09:00", "end_time": "10:00"},
            format="json",
        )
        self.session.refresh_from_db()
        self.assertEqual(self.session.start_time.strftime("%H:%M"), "06:00")

    def test_a_member_booking_does_not_take_its_price_from_the_browser(self):
        self.client.force_authenticate(self.me)
        resp = self.client.post(
            "/api/pt/sessions/",
            {
                "trainer": self.trainer.pk,
                "member": self.me.pk,
                "date": self.tomorrow.isoformat(),
                "start_time": "08:00",
                "end_time": "09:00",
                "price": "1.00",
            },
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(PTSession.objects.get(pk=resp.data["id"]).price, Decimal("0"))

    def test_staff_cannot_book_somebody_from_outside_the_gym(self):
        outsider = type(self.me).objects.create_user(
            username="outsider", email="outsider@example.com", password="pass12345"
        )
        self.client.force_authenticate(self.trainer)
        resp = self.client.post(
            "/api/pt/sessions/",
            {
                "trainer": self.trainer.pk,
                "member": outsider.pk,
                "date": self.tomorrow.isoformat(),
                "start_time": "08:00",
                "end_time": "09:00",
            },
        )
        self.assertIn(resp.status_code, (400, 404))
        self.assertFalse(PTSession.objects.filter(member=outsider).exists())


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class MassAssignmentPins(OneGymTestCase):
    """Fields a caller must never be able to set, whatever they post."""

    def setUp(self):
        super().setUp()
        self.me = self.person("me")
        self.admin = self.person("boss", Role.ADMIN)
        self.trainer = self.person("coach", Role.TRAINER)

    def test_the_profile_endpoint_ignores_role_staff_and_membership_fields(self):
        profile = MemberProfile.objects.get(user=self.me)
        before = (profile.membership_status, profile.join_date)
        self.client.force_authenticate(self.me)
        resp = self.client.patch(
            "/api/auth/me/",
            {
                "role": "admin",
                "is_staff": True,
                "is_superuser": True,
                "profile": {"membership_status": "active", "join_date": "2001-01-01"},
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.me.refresh_from_db()
        profile.refresh_from_db()
        self.assertEqual(self.me.role, Role.MEMBER)
        self.assertFalse(self.me.is_staff or self.me.is_superuser)
        self.assertEqual((profile.membership_status, profile.join_date), before)
        self.assertEqual(
            set(Membership.objects.filter(user=self.me).values_list("role", flat=True)),
            {Role.MEMBER},
        )

    def test_signing_up_cannot_choose_a_role_or_platform_flags(self):
        resp = self.client.post(
            "/api/auth/signup/",
            {
                "username": "climber",
                "email": "climber@example.com",
                "password": "Str0ng-passphrase-for-signup",
                "role": "admin",
                "is_staff": True,
                "is_superuser": True,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        user = type(self.me).objects.get(username="climber")
        self.assertEqual(user.role, Role.MEMBER)
        self.assertFalse(user.is_staff or user.is_superuser)
        self.assertEqual(
            set(Membership.objects.filter(user=user).values_list("role", flat=True)),
            {Role.MEMBER},
        )

    def test_an_admin_cannot_mint_platform_staff(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            "/api/auth/admin/users/",
            {
                "username": "newcoach",
                "email": "newcoach@example.com",
                "role": "trainer",
                "password": "Str0ng-passphrase-for-coach",
                "is_staff": True,
                "is_superuser": True,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        user = type(self.me).objects.get(username="newcoach")
        self.assertFalse(user.is_staff or user.is_superuser)

    def test_a_row_cannot_be_filed_under_another_gym_by_naming_it(self):
        _, elsewhere = founding_tenant("elsewhere")
        category = ExpenseCategory.objects.create(name="Utilities")
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            "/api/expenses/",
            {
                "category": category.pk,
                "amount": "10.00",
                "spent_on": timezone.localdate().isoformat(),
                "tenant": elsewhere.pk,
            },
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(Expense.unscoped.get(pk=resp.data["id"]).tenant_id, self.tenant.pk)

    def test_a_member_cannot_approve_their_own_upload(self):
        self.client.force_authenticate(self.me)
        resp = self.client.post(
            "/api/gallery/",
            {
                "media": SimpleUploadedFile("gym.png", png_bytes(), content_type="image/png"),
                "media_type": "image",
                "approved": "true",
            },
            format="multipart",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertFalse(GalleryPost.objects.get(pk=resp.data["id"]).approved)

    def test_a_member_cannot_file_a_referral_as_someone_else(self):
        self.client.force_authenticate(self.me)
        resp = self.client.post(
            "/api/referrals/",
            {
                "name": "Friend",
                "phone": "9000000002",
                "referrer": self.admin.pk,
                "referred_user": self.trainer.pk,
            },
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        referral = Referral.objects.get(pk=resp.data["id"])
        self.assertEqual(referral.referrer_id, self.me.pk)
        self.assertIsNone(referral.referred_user_id)


class ObjectReadPins(OneGymTestCase):
    """Guessing another member's ids within the same gym gets nothing."""

    def setUp(self):
        super().setUp()
        self.me = self.person("me")
        self.victim = self.person("victim")
        self.trainer = self.person("coach", Role.TRAINER)

    def test_a_member_cannot_read_another_members_invoice(self):
        plan = Plan.objects.create(name="Monthly", price=Decimal("1000"), duration_days=30)
        payment = record_payment(
            member=self.victim, plan=plan, amount=Decimal("1000"), method=PaymentMethod.CASH
        )
        invoice = issue_invoice(payment)
        self.client.force_authenticate(self.me)
        self.assertEqual(self.client.get(f"/api/invoices/{invoice.pk}/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/invoices/{invoice.pk}/pdf/").status_code, 404)

    def test_a_member_cannot_list_another_members_measurements(self):
        BodyMeasurement.objects.create(user=self.victim, weight_kg=Decimal("70"))
        self.client.force_authenticate(self.me)
        resp = self.client.get(f"/api/bodystats/measurements/?member={self.victim.pk}")
        rows = resp.data["results"] if isinstance(resp.data, dict) else resp.data
        self.assertEqual(rows, [])

    def test_a_trainer_cannot_read_an_unassigned_members_stats(self):
        self.client.force_authenticate(self.trainer)
        resp = self.client.get(f"/api/bodystats/summary/?member={self.victim.pk}")
        self.assertEqual(resp.status_code, 403)

    def test_a_member_cannot_read_someone_elses_check_in(self):
        visit = CheckInOut.objects.create(user=self.victim)
        self.client.force_authenticate(self.me)
        self.assertEqual(self.client.get(f"/api/attendance/{visit.pk}/").status_code, 404)
