from datetime import time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from core.testing import TenantAPIMixin, enrol

from accounts.models import MemberProfile, MembershipStatus, Role
from attendance.models import CheckInOut
from attendance.services import occupancy
from billing.models import DayPass, PaymentMethod, Plan
from billing.services import record_payment
from schedule_app.models import BookingStatus, ClassBooking, ClassSession

from . import kpis

User = get_user_model()
TODAY = timezone.localdate()


def make_member(username):
    user = User.objects.create_user(
        username=username, email=f"{username}@example.com", password="pass12345", role=Role.MEMBER
    )
    MemberProfile.objects.get_or_create(user=user)
    enrol(user)
    return user


class MrrTests(TenantAPIMixin, APITestCase):
    """Plans of different lengths have to be comparable."""

    def setUp(self):
        self.monthly = Plan.objects.create(
            name="Monthly", price=Decimal("1500"), duration_days=30
        )
        self.yearly = Plan.objects.create(
            name="Yearly", price=Decimal("14400"), duration_days=360
        )

    def test_a_monthly_plan_contributes_its_price(self):
        member = make_member("monthlypayer")
        record_payment(
            member=member, plan=self.monthly, amount=self.monthly.price,
            method=PaymentMethod.CASH,
        )
        self.assertEqual(kpis.mrr(), Decimal("1500.00"))

    def test_a_yearly_plan_is_spread_over_the_year(self):
        """14,400 over 360 days is 1,200 a month, not 14,400 in one."""
        member = make_member("yearlypayer")
        record_payment(
            member=member, plan=self.yearly, amount=self.yearly.price,
            method=PaymentMethod.CASH,
        )
        self.assertEqual(kpis.mrr(), Decimal("1200.00"))

    def test_an_expired_membership_contributes_nothing(self):
        member = make_member("lapsed")
        record_payment(
            member=member, plan=self.monthly, amount=self.monthly.price,
            method=PaymentMethod.CASH, paid_date=TODAY - timedelta(days=60),
        )
        self.assertEqual(kpis.mrr(), Decimal("0.00"))

    def test_arpm_is_mrr_over_the_members_paying_it(self):
        for name, plan in (("a", self.monthly), ("b", self.yearly)):
            record_payment(
                member=make_member(name), plan=plan, amount=plan.price,
                method=PaymentMethod.CASH,
            )
        # (1500 + 1200) / 2
        self.assertEqual(kpis.arpm(), Decimal("1350.00"))

    def test_arpm_with_nobody_paying_is_zero_not_a_crash(self):
        self.assertEqual(kpis.arpm(), Decimal("0.00"))

    def test_active_is_read_off_the_ledger_not_the_profile_flag(self):
        member = make_member("stale")
        record_payment(
            member=member, plan=self.monthly, amount=self.monthly.price,
            method=PaymentMethod.CASH,
        )
        # A profile that has not been swept still says expired.
        MemberProfile.objects.filter(user=member).update(
            membership_status=MembershipStatus.EXPIRED
        )
        self.assertEqual(len(kpis.active_members()), 1)


class ChurnRateTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.plan = Plan.objects.create(
            name="Monthly", price=Decimal("1500"), duration_days=30
        )
        self.start = TODAY - timedelta(days=60)
        self.end = TODAY

    def pay(self, member, days_ago):
        return record_payment(
            member=member, plan=self.plan, amount=self.plan.price,
            method=PaymentMethod.CASH, paid_date=TODAY - timedelta(days=days_ago),
        )

    def test_someone_who_lapsed_and_stayed_gone_counts(self):
        self.pay(make_member("gone"), 45)  # ended 15 days ago
        result = kpis.churn_rate(self.start, self.end)
        self.assertEqual(result["lapsed"], 1)
        self.assertEqual(result["rate"], 100.0)

    def test_someone_still_paid_up_does_not(self):
        self.pay(make_member("current"), 5)
        result = kpis.churn_rate(self.start, self.end)
        self.assertEqual(result["lapsed"], 0)

    def test_a_lapse_inside_the_grace_period_is_not_churn_yet(self):
        """Ended three days ago -- they may simply renew on Monday."""
        self.pay(make_member("justlapsed"), 33)
        self.assertEqual(kpis.churn_rate(self.start, self.end)["lapsed"], 0)

    def test_someone_who_renewed_is_not_counted(self):
        member = make_member("renewer")
        self.pay(member, 45)
        self.pay(member, 5)
        self.assertEqual(kpis.churn_rate(self.start, self.end)["lapsed"], 0)


class ClassFillTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.member = make_member("filler")
        self.day = TODAY - timedelta(days=1)

    def session(self, capacity):
        return ClassSession.objects.create(
            title="Class", date=self.day, start_time=time(9), end_time=time(10),
            capacity=capacity,
        )

    def test_seats_taken_against_seats_offered(self):
        session = self.session(10)
        ClassBooking.objects.create(
            member=self.member, session=session, status=BookingStatus.BOOKED
        )
        result = kpis.class_fill_rate(self.day, self.day)
        self.assertEqual((result["seats"], result["booked"], result["rate"]), (10, 1, 10.0))

    def test_an_uncapped_class_is_left_out_entirely(self):
        """It cannot be more or less full, so counting it either way is noise."""
        self.session(None)
        result = kpis.class_fill_rate(self.day, self.day)
        self.assertEqual(result["sessions"], 0)
        self.assertEqual(result["rate"], 0)

    def test_a_cancelled_booking_does_not_fill_a_seat(self):
        session = self.session(10)
        ClassBooking.objects.create(
            member=self.member, session=session, status=BookingStatus.CANCELLED
        )
        self.assertEqual(kpis.class_fill_rate(self.day, self.day)["booked"], 0)


class OccupancyTests(TenantAPIMixin, APITestCase):
    """Footfall by weekday and hour, counting everyone who came in."""

    def setUp(self):
        self.member = make_member("occupant")
        self.start = TODAY - timedelta(days=14)
        self.end = TODAY

    def visit(self, when, member=None, day_pass=None):
        # Closed on creation: leaving them open would trip the
        # one-open-check-in index on the second visit, which is the index
        # doing exactly what it should.
        record = CheckInOut.objects.create(
            user=member, day_pass=day_pass, check_out_time=when
        )
        CheckInOut.objects.filter(pk=record.pk).update(
            check_in_time=when, check_out_time=when + timedelta(hours=1)
        )
        return record

    def test_visits_land_in_the_right_weekday_and_hour(self):
        when = timezone.localtime().replace(hour=18, minute=30) - timedelta(days=7)
        self.visit(when, member=self.member)

        grid = occupancy(self.start, self.end)["grid"]
        self.assertEqual(grid[when.weekday()][18], 1)

    def test_guests_are_counted_too(self):
        """Their visits live in the same table precisely so this is right."""
        guest = DayPass.objects.create(name="Walk-in")
        when = timezone.localtime().replace(hour=11, minute=0) - timedelta(days=2)
        self.visit(when, day_pass=guest)

        result = occupancy(self.start, self.end)
        self.assertEqual(result["total_visits"], 1)
        self.assertEqual(result["grid"][when.weekday()][11], 1)

    def test_two_visits_in_one_day_are_two_visits(self):
        base = timezone.localtime().replace(hour=8, minute=0) - timedelta(days=3)
        self.visit(base, member=self.member)
        self.visit(base + timedelta(hours=9), member=self.member)
        self.assertEqual(occupancy(self.start, self.end)["total_visits"], 2)

    def test_the_busiest_hour_is_reported(self):
        when = timezone.localtime().replace(hour=19, minute=0) - timedelta(days=5)
        for _ in range(3):
            self.visit(when, day_pass=DayPass.objects.create(name="G"))

        busiest = occupancy(self.start, self.end)["busiest"]
        self.assertEqual(busiest["hour"], 19)
        self.assertEqual(busiest["visits"], 3)

    def test_an_empty_window_is_an_honest_zero(self):
        result = occupancy(self.start, self.end)
        self.assertEqual(result["total_visits"], 0)
        self.assertIsNone(result["busiest"])
        self.assertEqual(len(result["grid"]), 7)


class KpiApiTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="kpiadmin", email="k@example.com", password="pass12345", role=Role.ADMIN
        )
        self.member = make_member("kpimember")

    def test_members_cannot_read_the_owner_dashboard(self):
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get("/api/reports/kpis/").status_code, 403)
        self.assertEqual(self.client.get("/api/reports/occupancy/").status_code, 403)

    def test_an_admin_gets_every_headline_number(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.get("/api/reports/kpis/")
        self.assertEqual(resp.status_code, 200)
        for key in ("mrr", "arpm", "active_members", "churn", "pt", "classes"):
            self.assertIn(key, resp.data)

    def test_every_metric_states_what_it_counts(self):
        """A number with no definition is worse than no number."""
        self.client.force_authenticate(self.admin)
        definitions = self.client.get("/api/reports/kpis/").data["definitions"]
        self.assertIn("30 days", definitions["mrr"])
        self.assertIn("7 days", definitions["churn"])

    def test_the_heatmap_comes_back_as_a_week_of_hours(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.get("/api/reports/occupancy/")
        self.assertEqual(len(resp.data["grid"]), 7)
        self.assertEqual(len(resp.data["grid"][0]), 24)
