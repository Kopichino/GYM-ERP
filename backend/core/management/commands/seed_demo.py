"""Populate the database with a coherent demo gym.

Every screen in all three portals has something to show: members with different
membership states, workout and body-composition history that actually trends,
a class with a waitlist, a device with an unmatched punch, and a moderation
queue that isn't empty.

Safe to re-run -- it upserts by username/name, and `--wipe` removes everything
it created. Demo accounts are recognisable by their @ironcore.demo address, so
the wipe never touches real data.

Everything lands in one gym. Which gym is resolved once, up front, and held
in scope for the whole run -- every model this touches is tenant-scoped, and
`Model.objects` raises rather than guessing when nothing is in scope.

    python manage.py seed_demo
    python manage.py seed_demo --wipe
    python manage.py seed_demo --tenant northside-main
"""

import io
import random
from datetime import date, time, timedelta
from decimal import Decimal

from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts import mfa
from accounts.models import MembershipStatus, MemberProfile, MfaDevice, Role, User
from tenancy import context
from tenancy.models import Membership, Organisation, Tenant
from announcements.models import Announcement
from attendance.models import CheckInMethod, CheckInOut
from billing.models import DayPass, Discount, DiscountType, PaymentMethod, Plan
from branding.models import Branding
from billing.services import record_payment
from commissions.models import CommissionRule
from expenses.models import Expense, ExpenseCategory
from gamification.models import Badge, GamificationProfile, MemberBadge, PersonalRecord
from invoicing.models import Invoice
from invoicing.services import issue_invoice
from nutrition.models import DietDay, DietGoal, DietMeal, DietMealItem, DietPlan, FoodItem
from referrals.models import Referral, ReferralProgram
from referrals.services import code_for, grant_reward
from crm.models import Enquiry, EnquiryNote, EnquirySource, EnquiryStatus
from bodystats.models import BodyMeasurement, GoalStatus, GoalType, MemberGoal
from devices.models import Device, DeviceKind, generate_key
from devices.services import record_punch
from gallery.models import GalleryPost, MediaType
from schedule_app.models import ClassSession
from schedule_app.services import book
from feedback.models import Survey, SurveyResponse, Trigger
from pt.models import Availability, PTSession, Unavailable
from shifts.models import Position, Shift
from workouts.models import (
    Exercise,
    SplitDay,
    SplitExercise,
    WorkoutLog,
    WorkoutSession,
    WorkoutSplit,
)

DEMO_DOMAIN = "ironcore.demo"
PASSWORD = "IronDemo123!"
#: One authenticator key shared by every demo account, printed at the end.
#: Two-step sign-in is required, and a demo that stops at "set up your
#: authenticator" for every role is not much of a demo. Published on purpose,
#: exactly like the password above -- demo accounts only, never a real one.
DEMO_MFA_SECRET = "JBSWY3DPEHPK3PXPIRONCOREDEMOKEY2"

TODAY = date.today()


def demo_email(handle):
    return f"{handle}@{DEMO_DOMAIN}"


def png(color, size=(640, 480)):
    """A small solid-colour image, so gallery and profile photos are real files
    rather than broken links."""
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return ContentFile(buffer.getvalue())


class Command(BaseCommand):
    help = "Seed a full demo gym across every feature. Use --wipe to remove it."

    def add_arguments(self, parser):
        parser.add_argument(
            "--wipe", action="store_true", help="Delete demo data instead of creating it."
        )
        parser.add_argument(
            "--tenant",
            default=None,
            help=(
                "Slug of the gym to seed into. Defaults to the founding branch "
                "-- the one the backfill migration created."
            ),
        )

    def handle(self, *args, **options):
        random.seed(7)  # stable output between runs

        # Resolved before anything touches the ORM, and held for the whole run.
        #
        # Nearly every model below is tenant-scoped, and a scoped manager
        # raises rather than guessing when nothing is in scope -- so this
        # command failed on its first query until it said which gym it meant.
        # One scope around everything rather than one per step: the steps call
        # into services (record_payment, issue_invoice, book, ...) that touch
        # scoped models of their own, and those would need it too.
        tenant = self._tenant(options["tenant"])

        with context.scope(tenant):
            if options["wipe"]:
                self._wipe()
                return

            with transaction.atomic():
                self._branding()
                self._exercises()
                plans = self._plans()
                admin = self._admin()
                trainers = self._trainers()
                members = self._members(trainers)
                self._offers(plans)
                self._billing(members, plans, admin)
                self._invoices(members)
                self._expenses(admin)
                self._attendance(members)
                self._workouts(members)
                self._splits(members)
                self._diets(members, trainers)
                self._bodystats(members, trainers)
                self._gamification(members)
                self._announcements(admin)
                classes = self._classes(trainers)
                self._bookings(classes, members)
                self._gallery(members)
                self._devices(members)
                self._shifts(admin, trainers)
                self._day_passes(admin)
                self._pt(members, trainers)
                self._feedback(members)
                self._enquiries(admin)
                self._referrals(members, admin)

            self._report(admin, trainers, members)

    # --------------------------------------------------------------- tenant

    def _tenant(self, slug):
        """The gym everything below belongs to.

        Defaults to the founding branch -- the one the backfill migration
        created from whatever the gym was called before multi-tenancy. Ordering
        by id rather than picking arbitrarily, because on a platform with
        several gyms "the first one" should mean the original, not whichever
        row the database happened to return.

        Creates one only when there are none at all, which happens on a
        database migrated from empty. Seeding is the first thing anyone runs on
        a fresh checkout, and failing with "no tenant exists" would be a riddle
        rather than an error.
        """
        if slug:
            try:
                return Tenant.objects.get(slug=slug)
            except Tenant.DoesNotExist:
                raise CommandError(
                    f"No gym with slug {slug!r}. Existing: "
                    + (", ".join(Tenant.objects.values_list("slug", flat=True)) or "none")
                )

        tenant = Tenant.objects.order_by("id").first()
        if tenant:
            return tenant

        org, _ = Organisation.objects.get_or_create(
            slug="ironcore", defaults={"name": "IRONCORE"}
        )
        tenant, _ = Tenant.objects.get_or_create(
            slug="ironcore-main", defaults={"organisation": org, "name": "IRONCORE"}
        )
        self.stdout.write(f"Created gym {tenant.slug} to seed into.")
        return tenant

    # ------------------------------------------------------------------ wipe

    def _wipe(self):
        demo_users = User.objects.filter(email__endswith=f"@{DEMO_DOMAIN}")
        count = demo_users.count()

        Device.objects.filter(serial__startswith="DEMO-").delete()
        Expense.objects.filter(notes__startswith="[demo]").delete()
        ExpenseCategory.objects.filter(description__startswith="[demo]").delete()
        Discount.objects.filter(description__startswith="[demo]").delete()
        DayPass.objects.filter(notes__startswith="[demo]").delete()
        ReferralProgram.objects.filter(blurb__startswith="[demo]").delete()
        # Keyed on the demo email rather than the tagline: the tagline is
        # shown to members on the login screen, so it must read cleanly.
        Branding.objects.filter(email__endswith=f"@{DEMO_DOMAIN}").delete()
        # Diet plans cascade from the member; the food catalogue is shared
        # and left alone, the same way the exercise catalogue is.
        # Commission entries and invoices cascade from the payments, which
        # cascade from the members deleted below.
        CommissionRule.objects.filter(trainer__in=demo_users).delete()
        Shift.objects.filter(staff__in=demo_users).delete()
        # Responses cascade from the member; the questions are seeded rows
        # of their own, so they are swept by their titles.
        Survey.objects.filter(title__startswith="[demo] ").delete()
        # Metrics and connections cascade from the member accounts below.
        # Availability, blocks and sessions all cascade from the accounts
        # deleted below; nothing extra to sweep.
        Enquiry.objects.filter(created_by__in=demo_users).delete()
        ClassSession.objects.filter(title__startswith="[demo] ").delete()
        Announcement.objects.filter(title__startswith="[demo] ").delete()
        GalleryPost.objects.filter(uploader__in=demo_users).delete()
        # Payments cascade from the member; plans are shared so only demo ones go.
        demo_users.delete()
        Plan.objects.filter(description__startswith="[demo]").delete()

        self.stdout.write(self.style.SUCCESS(f"Removed {count} demo accounts and their data."))

    # -------------------------------------------------------------- identity

    def _branding(self):
        """The gym's own name and colours, so the demo shows what a white-label
        install looks like rather than the product's defaults."""
        if Branding.objects.exists():
            return
        Branding.objects.create(
            name="IRONCORE",
            tagline="Train hard. Track everything.",
            accent="#ff3d5a",
            accent_2="#ffb020",
            phone="+91 98200 40000",
            email="frontdesk@ironcore.demo",
            address="12 Anchor Street\nAndheri West\nMumbai 400053",
            website="https://ironcore.demo",
            instagram="ironcore.gym",
            # Read by the public website's footer, one row per line.
            opening_hours="Monday to Friday: 5:30 - 23:00\nSaturday: 6:00 - 21:00\nSunday: 7:00 - 20:00",
            gstin="27AAAAA0000A1Z5",
            state="Maharashtra",
        )

    # ------------------------------------------------------------- catalogue

    def _exercises(self):
        if Exercise.objects.exists():
            self.stdout.write(f"Exercise catalog already has {Exercise.objects.count()} entries.")
            return
        self.stdout.write("Importing the bundled exercise catalog...")
        call_command("import_exercises")

    def _plans(self):
        specs = [
            ("Monthly", Decimal("1500.00"), 30, "Rolling monthly membership."),
            ("Quarterly", Decimal("4000.00"), 90, "Three months, billed up front."),
            ("Annual", Decimal("14000.00"), 365, "Best value -- twelve months."),
        ]
        plans = {}
        for name, price, days, blurb in specs:
            plan, _ = Plan.objects.update_or_create(
                name=name,
                defaults={
                    "price": price,
                    "duration_days": days,
                    "description": f"[demo] {blurb}",
                    "is_active": True,
                },
            )
            plans[name] = plan
        return plans

    # -------------------------------------------------------------- accounts

    def _account(self, handle, first, last, role, **profile):
        user, _ = User.objects.update_or_create(
            username=handle,
            defaults={
                "email": demo_email(handle),
                "first_name": first,
                "last_name": last,
                "role": role,
            },
        )
        user.set_password(PASSWORD)
        user.save()
        MemberProfile.objects.update_or_create(user=user, defaults=profile)

        # Without this the account exists and can log in, and then sees nothing.
        #
        # Since multi-tenancy, what someone may do is read off Membership at
        # this gym rather than off `User.role` -- so a demo user created after
        # the backfill migration ran had no access anywhere. It looked correct
        # on any machine seeded *before* the conversion, because the backfill
        # had already given those accounts a membership.
        Membership.objects.get_or_create(
            user=user,
            tenant=context.require(),
            role=role,
        )
        # Add DEMO_MFA_SECRET to an authenticator app once and it signs in as
        # any demo account.
        MfaDevice.objects.update_or_create(
            user=user,
            defaults={
                "secret": DEMO_MFA_SECRET,
                "pending_secret": "",
                "confirmed_at": timezone.now(),
                "last_used_step": None,
            },
        )
        return user

    def _admin(self):
        return self._account("demo.admin", "Nisha", "Rao", Role.ADMIN, phone="+91 98200 10000")

    def _trainers(self):
        specs = [
            ("coach.ravi", "Ravi", "Kumar", "Strength & Conditioning",
             "Ten years coaching powerlifting and general strength. Believes in boring, repeatable programming."),
            ("coach.meera", "Meera", "Iyer", "Yoga & Mobility",
             "Certified Hatha instructor. Works mostly with members returning from injury."),
        ]
        trainers = []
        for handle, first, last, specialty, bio in specs:
            user = self._account(handle, first, last, Role.TRAINER, phone="+91 98200 20000")
            # (user, specialty): the specialty is only used in the summary printed
            # at the end -- there is no instructor profile to hold it any more.
            trainers.append((user, specialty))
        return trainers

    def _members(self, trainers):
        ravi, meera = trainers[0][0], trainers[1][0]
        specs = [
            # handle, first, last, trainer, height, joined days ago, biometric
            ("arjun.s", "Arjun", "Sharma", ravi, 178, 400, "FP-1001"),
            ("priya.n", "Priya", "Nair", meera, 163, 300, "FP-1002"),
            ("rahul.v", "Rahul", "Verma", ravi, 181, 500, "FP-1003"),
            ("sneha.k", "Sneha", "Kulkarni", meera, 158, 200, "FP-1004"),
            ("vikram.r", "Vikram", "Reddy", None, None, 3, "FP-1005"),
            # Was a regular, has quietly stopped coming -- the softer of the
            # two retention bands.
            ("meena.d", "Meena", "Desai", meera, 166, 120, None),
        ]
        members = {}
        for handle, first, last, trainer, height, joined_ago, biometric in specs:
            user = self._account(
                handle,
                first,
                last,
                Role.MEMBER,
                phone=f"+91 98{random.randint(100000000, 999999999)}"[:16],
                trainer=trainer,
                height_cm=height,
                biometric_id=biometric,
                date_of_birth=date(1990 + random.randint(0, 8), random.randint(1, 12), 15),
                emergency_contact_name=f"{last} family",
                emergency_contact_phone="+91 98200 99999",
            )
            # join_date is auto_now_add, so backdating needs a direct update.
            MemberProfile.objects.filter(user=user).update(
                join_date=TODAY - timedelta(days=joined_ago)
            )
            members[handle] = user
        return members

    # --------------------------------------------------------------- billing

    def _billing(self, members, plans, admin):
        """Membership status is derived from these payments -- it is never set
        directly, so the ledger and the badge can't disagree."""
        ledger = [
            # member, plan, paid days ago -> leaves them active
            ("arjun.s", "Quarterly", 20),
            ("arjun.s", "Quarterly", 110),
            ("priya.n", "Monthly", 10),
            ("priya.n", "Monthly", 40),
            ("rahul.v", "Monthly", 95),   # lapsed -> expires on its own
            ("sneha.k", "Monthly", 15),
        ]
        for handle, plan_name, days_ago in ledger:
            member = members[handle]
            paid = TODAY - timedelta(days=days_ago)
            already = member.payments.filter(paid_date=paid).exists()
            if already:
                continue
            record_payment(
                member=member,
                plan=plans[plan_name],
                amount=plans[plan_name].price,
                method=random.choice(
                    [PaymentMethod.UPI, PaymentMethod.CASH, PaymentMethod.CARD]
                ),
                paid_date=paid,
                notes="[demo] Seeded payment.",
                recorded_by=admin,
            )

        # Sneha is on a hold the ledger cannot express -- the one status an
        # admin sets by hand.
        MemberProfile.objects.filter(user=members["sneha.k"]).update(
            membership_status=MembershipStatus.PAUSED
        )
        # Vikram has walked in but not paid yet: no payments, no derived status.

    # ---------------------------------------------------------------- offers

    def _offers(self, plans):
        """Codes the front desk can type at checkout. `times_used` is derived
        from the payment ledger, so nothing is pre-counted here."""
        specs = [
            # code, type, value, plan names (empty = every plan), days valid, max uses
            ("NEWYEAR25", DiscountType.PERCENT, Decimal("25"), [], 60, 100),
            ("FRIEND500", DiscountType.FLAT, Decimal("500"), [], 180, None),
            ("YEARLY15", DiscountType.PERCENT, Decimal("15"), ["Yearly"], 90, 50),
            ("STUDENT10", DiscountType.PERCENT, Decimal("10"), ["Monthly", "Quarterly"], 365, None),
            ("LAPSED2024", DiscountType.FLAT, Decimal("1000"), [], -30, 20),  # already expired
        ]
        for code, kind, value, plan_names, days, max_uses in specs:
            discount, created = Discount.objects.get_or_create(
                code=code,
                defaults={
                    "description": "[demo] Seeded offer.",
                    "discount_type": kind,
                    "value": value,
                    "valid_from": TODAY - timedelta(days=30),
                    "valid_until": TODAY + timedelta(days=days),
                    "max_uses": max_uses,
                    "max_uses_per_member": 1,
                },
            )
            if created and plan_names:
                discount.plans.set([plans[name] for name in plan_names if name in plans])

    # -------------------------------------------------------------- invoices

    def _invoices(self, members):
        """Issue the GST invoice for every seeded payment. Numbering is gapless
        within a financial year, so this walks payments oldest-first."""
        payments = sorted(
            (p for member in members.values() for p in member.payments.all()),
            key=lambda p: (p.paid_date, p.id),
        )
        for payment in payments:
            issue_invoice(payment)

    # -------------------------------------------------------------- expenses

    def _expenses(self, admin):
        if Expense.objects.filter(notes__startswith="[demo]").exists():
            return
        categories = {}
        for name in ["Rent", "Salaries", "Equipment", "Utilities", "Marketing", "Maintenance"]:
            categories[name], _ = ExpenseCategory.objects.get_or_create(
                name=name, defaults={"description": "[demo] Seeded category."}
            )
        specs = [
            # category, amount, days ago, vendor
            ("Rent", "45000", 5, "Shreeji Properties"),
            ("Rent", "45000", 35, "Shreeji Properties"),
            ("Salaries", "68000", 3, "Payroll"),
            ("Salaries", "68000", 33, "Payroll"),
            ("Equipment", "22500", 12, "FitKart Wholesale"),
            ("Equipment", "8400", 48, "FitKart Wholesale"),
            ("Utilities", "9800", 7, "State electricity board"),
            ("Utilities", "10450", 38, "State electricity board"),
            ("Marketing", "6000", 9, "Local print and social ads"),
            ("Maintenance", "3200", 18, "AquaClean Services"),
            ("Maintenance", "1500", 2, "Treadmill belt service"),
        ]
        for index, (category, amount, days_ago, vendor) in enumerate(specs, start=1):
            Expense.objects.create(
                category=categories[category],
                amount=Decimal(amount),
                spent_on=TODAY - timedelta(days=days_ago),
                vendor=vendor,
                reference="DEMO-BILL-%03d" % index,
                notes="[demo] Seeded expense.",
                recorded_by=admin,
            )

    # ------------------------------------------------------------ attendance

    def _attendance(self, members):
        if CheckInOut.objects.filter(user__email__endswith=DEMO_DOMAIN).exists():
            return

        plans = {
            # handle: (days back, chance of visiting, streak tail, quiet since)
            # `quiet since` drops every visit newer than that many days ago, so
            # the retention list has someone real to chase rather than being
            # empty in the demo.
            "arjun.s": (60, 0.55, 4, 0),
            "priya.n": (60, 0.4, 2, 0),
            # Lapsed payment and stopped turning up -- the call the front desk
            # most wants to be prompted about.
            "rahul.v": (60, 0.3, 0, 24),
            # Paused by an admin, so deliberately absent from the retention
            # list -- chasing someone who told us they are away is worse
            # than saying nothing.
            "sneha.k": (45, 0.3, 0, 12),
            "vikram.r": (3, 0.5, 1, 0),
            # In regularly until a week ago: the "cooling off" band.
            "meena.d": (60, 0.45, 0, 6),
        }

        for handle, (window, chance, streak, quiet_since) in plans.items():
            member = members[handle]
            visit_days = {d for d in range(1, window) if random.random() < chance}
            # A run ending today so the streak counter shows something real.
            visit_days |= set(range(0, streak))
            if quiet_since:
                # Pinned to the boundary rather than left to the dice: the
                # nearest surviving random visit could land anywhere, which
                # made which retention band a member demonstrated a lottery.
                visit_days = {d for d in visit_days if d > quiet_since}
                visit_days.add(quiet_since)

            for days_ago in sorted(visit_days, reverse=True):
                # Mid-day only, on purpose. The server stores UTC while the
                # browser renders in the viewer's zone, so a 19:00 session seeded
                # under the default TIME_ZONE=UTC reappears after midnight the
                # next day -- putting two visits on one date and breaking the
                # streak count. Hours 9-14 stay on the intended day either side
                # of UTC. (Set TIME_ZONE to the gym's own zone in production and
                # this stops being a concern.)
                local_day = timezone.localtime() - timedelta(days=days_ago)
                start = local_day.replace(
                    hour=random.choice([9, 10, 11, 12, 13, 14]),
                    minute=random.choice([0, 15, 30]),
                    second=0,
                    microsecond=0,
                )
                record = CheckInOut.objects.create(
                    user=member,
                    method=CheckInMethod.BIOMETRIC if member.profile.biometric_id else CheckInMethod.TAP,
                )
                # check_in_time is auto_now_add; today's visit is left open so
                # the dashboard shows a live timer for at least one member.
                CheckInOut.objects.filter(pk=record.pk).update(
                    check_in_time=start,
                    check_out_time=None
                    if (days_ago == 0 and handle == "arjun.s")
                    else start + timedelta(minutes=random.randint(45, 95)),
                )

    # -------------------------------------------------------------- workouts

    def _workouts(self, members):
        if WorkoutSession.objects.filter(user__email__endswith=DEMO_DOMAIN).exists():
            return

        # Progressive overload so the trend line actually climbs.
        programmes = {
            "arjun.s": [
                ("Barbell Bench Press", 60, 2.5, 8),
                ("Barbell Back Squat", 80, 5, 6),
                ("Deadlift", 100, 5, 5),
            ],
            "priya.n": [
                ("Dumbbell Shoulder Press", 12, 1, 12),
                ("Leg Press", 60, 5, 12),
                ("Deadlift", 55, 2.5, 8),
            ],
            "rahul.v": [("Barbell Bench Press", 55, 2.5, 8), ("Deadlift", 80, 5, 5)],
            # Five members on the deadlift on purpose: the private "just for
            # me" standing refuses to place anybody in a pool smaller than
            # five, so a demo with three lifters would only ever show the
            # privacy guard and never the feature behind it.
            "sneha.k": [("Deadlift", 70, 2.5, 6), ("Leg Press", 50, 5, 12)],
            "meena.d": [("Deadlift", 60, 2.5, 8)],
        }

        for handle, programme in programmes.items():
            member = members[handle]
            # Down to week 0, i.e. a session today: stopping a week short
            # meant the heaviest lift -- and so the newest personal record --
            # was always in last month, leaving this month's leaderboard
            # empty in a fresh demo.
            for week in range(8, -1, -1):
                session = WorkoutSession.objects.create(user=member, notes="[demo] Seeded session.")
                session_date = TODAY - timedelta(weeks=week)
                WorkoutSession.objects.filter(pk=session.pk).update(date=session_date)

                for name, base, step, reps in programme:
                    exercise = Exercise.objects.filter(name=name).first()
                    if not exercise:
                        continue
                    weight = Decimal(str(base)) + Decimal(str(step)) * (8 - week)
                    for set_no in range(1, 4):
                        WorkoutLog.objects.create(
                            session=session,
                            exercise=exercise,
                            set_number=set_no,
                            reps=reps,
                            weight=weight,
                            weight_unit="kg",
                        )

    # ---------------------------------------------------------------- splits

    def _splits(self, members):
        if WorkoutSplit.objects.filter(user__email__endswith=DEMO_DOMAIN).exists():
            return

        # Arjun runs a 4-day push/pull/legs/upper; Priya a 3-day full-body.
        # Both include today, so the check-in screen has something to show
        # whichever day the demo is opened on.
        today = TODAY.weekday()
        plans = {
            "arjun.s": (
                "Push / Pull / Legs",
                [
                    (today, "Push", ["Chest", "Shoulders", "Triceps"]),
                    ((today + 1) % 7, "Pull", ["Back", "Biceps"]),
                    ((today + 2) % 7, "Legs", ["Legs"]),
                    ((today + 4) % 7, "Upper", ["Chest", "Back", "Shoulders"]),
                ],
            ),
            "priya.n": (
                "Full body 3x",
                [
                    (today, "Full body", ["Legs", "Back", "Abs"]),
                    ((today + 2) % 7, "Full body", ["Chest", "Shoulders", "Abs"]),
                    ((today + 4) % 7, "Full body", ["Legs", "Biceps", "Abs"]),
                ],
            ),
        }

        for handle, (name, days) in plans.items():
            split = WorkoutSplit.objects.create(user=members[handle], name=name, is_active=True)
            for weekday, label, muscles in days:
                day = SplitDay.objects.create(
                    split=split, weekday=weekday, label=label, target_muscles=muscles
                )
                # Pull a few real catalog entries for the muscles targeted.
                picks = list(
                    Exercise.objects.filter(muscle_group__in=muscles).order_by("name")[:4]
                )
                for order, exercise in enumerate(picks, start=1):
                    SplitExercise.objects.create(
                        day=day,
                        exercise=exercise,
                        order=order,
                        target_sets=random.choice([3, 4]),
                        target_reps=random.choice(["6-8", "8-12", "10-12"]),
                    )

    # ------------------------------------------------------------- nutrition

    def _diets(self, members, trainers):
        """Two members eat to a plan, one written by their trainer.

        Every calorie shown in the app is derived from these grams, so nothing
        totals anything here -- the numbers appear when the plan is read.
        """
        if DietPlan.objects.exists():
            return
        if not FoodItem.objects.exists():
            call_command("import_foods")

        def food(name):
            return FoodItem.objects.filter(name=name).first()

        # meal type -> [(food name, grams)]
        training_day = [
            ("breakfast", [("Oats (dry)", 80), ("Milk (toned)", 240), ("Banana", 120)]),
            ("snack_am", [("Almonds", 24), ("Apple", 180)]),
            ("lunch", [("Boiled rice", 200), ("Chicken breast (cooked)", 180), ("Mixed salad", 100)]),
            ("post_workout", [("Whey protein (powder)", 30), ("Dates", 24)]),
            ("dinner", [("Roti (whole wheat)", 80), ("Toor dal (cooked)", 200), ("Curd (plain)", 150)]),
        ]
        rest_day = [
            ("breakfast", [("Egg (whole)", 100), ("Whole wheat bread", 60)]),
            ("lunch", [("Brown rice", 150), ("Rajma (cooked)", 180), ("Cucumber", 100)]),
            ("dinner", [("Paneer", 120), ("Broccoli", 150), ("Roti (whole wheat)", 40)]),
        ]
        yoga_day = [
            ("breakfast", [("Poha (dry)", 90), ("Papaya", 150)]),
            ("lunch", [("Boiled rice", 150), ("Tofu", 150), ("Spinach", 60)]),
            ("snack_pm", [("Greek yoghurt", 170), ("Walnuts", 15)]),
            ("dinner", [("Roti (whole wheat)", 40), ("Chana / chickpeas (cooked)", 165)]),
        ]

        specs = [
            # member, plan name, goal, target kcal, author, weekday -> meals
            (
                "arjun.s",
                "Lean bulk",
                DietGoal.BULK,
                2900,
                trainers[0][0],
                {0: training_day, 2: training_day, 4: training_day, 1: rest_day, 3: rest_day},
            ),
            (
                "priya.n",
                "Maintenance",
                DietGoal.MAINTAIN,
                1900,
                trainers[1][0] if len(trainers) > 1 else trainers[0][0],
                {0: yoga_day, 2: yoga_day, 4: yoga_day, 5: rest_day},
            ),
        ]

        for handle, name, goal, target, author, week in specs:
            plan = DietPlan.objects.create(
                user=members[handle],
                name=name,
                goal=goal,
                target_calories=target,
                created_by=author,
                notes="[demo] Seeded plan.",
                is_active=True,
            )
            for weekday, meals in week.items():
                day = DietDay.objects.create(
                    plan=plan,
                    weekday=weekday,
                    label="Training day" if meals is not rest_day else "Rest day",
                )
                for order, (meal_type, items) in enumerate(meals, start=1):
                    meal = DietMeal.objects.create(day=day, meal_type=meal_type, order=order)
                    for item_order, (food_name, grams) in enumerate(items, start=1):
                        item = food(food_name)
                        if item:
                            DietMealItem.objects.create(
                                meal=meal,
                                food=item,
                                quantity_g=Decimal(grams),
                                order=item_order,
                            )

    # ------------------------------------------------------------- bodystats

    def _bodystats(self, members, trainers):
        if BodyMeasurement.objects.filter(user__email__endswith=DEMO_DOMAIN).exists():
            return

        ravi = trainers[0][0]
        journeys = {
            # handle: (start weight, weekly change, body fat start)
            "arjun.s": (Decimal("84.0"), Decimal("-0.5"), Decimal("24.0")),
            "priya.n": (Decimal("58.0"), Decimal("0.3"), Decimal("27.0")),
            "rahul.v": (Decimal("92.0"), Decimal("-0.2"), Decimal("30.0")),
            # Weighed because a lift with no bodyweight behind it is left out
            # of every ratio -- deliberately, since inventing one would put
            # somebody where they did not earn it.
            "sneha.k": (Decimal("66.0"), Decimal("-0.1"), Decimal("28.0")),
            "meena.d": (Decimal("71.0"), Decimal("-0.3"), Decimal("31.0")),
        }

        for handle, (start, weekly, fat) in journeys.items():
            member = members[handle]
            for week in range(8, -1, -1):
                BodyMeasurement.objects.create(
                    user=member,
                    recorded_on=TODAY - timedelta(weeks=week),
                    weight_kg=start + weekly * (8 - week),
                    body_fat_pct=fat - Decimal("0.4") * (8 - week),
                    notes="",
                    # Ravi weighs his own members in; Priya logs her own.
                    recorded_by=ravi if handle == "arjun.s" else None,
                )

        # An in-progress goal, an achieved one, and an attendance target.
        MemberGoal.objects.get_or_create(
            user=members["arjun.s"],
            goal_type=GoalType.WEIGHT,
            defaults={
                "start_value": Decimal("84.0"),
                "target_value": Decimal("78.0"),
                "target_date": TODAY + timedelta(days=60),
            },
        )
        MemberGoal.objects.get_or_create(
            user=members["arjun.s"],
            goal_type=GoalType.ATTENDANCE,
            defaults={"start_value": Decimal("0"), "target_value": Decimal("12")},
        )
        MemberGoal.objects.get_or_create(
            user=members["priya.n"],
            goal_type=GoalType.WEIGHT,
            defaults={
                "start_value": Decimal("58.0"),
                "target_value": Decimal("60.0"),
                "status": GoalStatus.ACHIEVED,
            },
        )
        MemberGoal.objects.get_or_create(
            user=members["rahul.v"],
            goal_type=GoalType.CUSTOM,
            defaults={
                "title": "Touch toes without bending knees",
                "target_value": Decimal("1"),
                "current_value": Decimal("0"),
            },
        )

    # ---------------------------------------------------------- gamification

    def _gamification(self, members):
        """Badges, records and who is on the leaderboard.

        Nothing is invented here: the badge ladder is loaded, two members opt
        in, and then the real services derive their records from the workout
        logs and award whatever those numbers earn -- so the demo shows the
        actual mechanism rather than a hand-placed result.
        """
        if not Badge.objects.exists():
            call_command("import_badges")

        # Opt-in is off by default and stays that way for the others, which is
        # the point of the setting.
        for handle in ("arjun.s", "priya.n"):
            GamificationProfile.objects.get_or_create(
                user=members[handle], defaults={"leaderboard_opt_in": True}
            )

        if MemberBadge.objects.exists():
            return
        from gamification import awards, records as record_service

        for member in members.values():
            record_service.sync_records(member)
            awards.evaluate(member)

        # Leave exactly one uncelebrated record each, so the demo shows the
        # "new PR" moment as a member who opens the app regularly would see it.
        # Left alone, the seeder's last three weeks of progressive overload all
        # fall inside the celebration window and pile up nine at once -- correct
        # behaviour for somebody who has not logged in for a fortnight, and a
        # poor first impression of the feature.
        for member in members.values():
            theirs = PersonalRecord.objects.filter(member=member)
            theirs.update(seen_at=timezone.now())
            newest = theirs.order_by("-achieved_on", "-weight_kg").first()
            if newest is not None:
                PersonalRecord.objects.filter(pk=newest.pk).update(seen_at=None)

    # --------------------------------------------------------------- content

    def _announcements(self, admin):
        specs = [
            ("[demo] Gym closed on Republic Day",
             "We're shut on 26 January. Normal hours resume the following morning.", True),
            ("[demo] New squat racks on the floor",
             "Two more racks are in, so the 6pm queue should finally ease up.", False),
            ("[demo] Personal training slots open",
             "Ravi and Meera both have weekday morning slots free. Ask at the desk.", False),
        ]
        for title, body, pinned in specs:
            Announcement.objects.update_or_create(
                title=title, defaults={"body": body, "pinned": pinned, "created_by": admin}
            )

    def _classes(self, trainers):
        ravi, meera = trainers[0][0], trainers[1][0]
        specs = [
            ("[demo] Morning HIIT", ravi, 1, time(7, 0), time(8, 0), 12),
            ("[demo] Strength Basics", ravi, 2, time(18, 30), time(19, 30), 8),
            ("[demo] Sunrise Yoga", meera, 2, time(6, 30), time(7, 30), None),
            ("[demo] Mobility Clinic", meera, 4, time(19, 0), time(20, 0), 2),
            ("[demo] Saturday Circuit", ravi, 6, time(9, 0), time(10, 0), 15),
            ("[demo] Last week's HIIT", ravi, -5, time(7, 0), time(8, 0), 12),
        ]
        classes = {}
        for title, trainer, offset, start, end, capacity in specs:
            session, _ = ClassSession.objects.update_or_create(
                title=title,
                defaults={
                    "trainer": trainer,
                    "date": TODAY + timedelta(days=offset),
                    "start_time": start,
                    "end_time": end,
                    "capacity": capacity,
                    "description": "Seeded demo class.",
                },
            )
            classes[title] = session
        return classes

    def _bookings(self, classes, members):
        # Mobility Clinic seats 2, so the third booking demonstrates the
        # waitlist and the position counter.
        wanted = [
            ("[demo] Morning HIIT", ["arjun.s", "priya.n"]),
            ("[demo] Sunrise Yoga", ["priya.n", "sneha.k"]),
            ("[demo] Mobility Clinic", ["priya.n", "sneha.k", "arjun.s"]),
            ("[demo] Strength Basics", ["arjun.s"]),
        ]
        for title, handles in wanted:
            session = classes[title]
            for handle in handles:
                try:
                    book(session.pk, members[handle])
                except Exception:
                    # Already booked from a previous run.
                    continue

    def _gallery(self, members):
        if GalleryPost.objects.filter(uploader__email__endswith=DEMO_DOMAIN).exists():
            return
        specs = [
            ("arjun.s", "First 100kg deadlift. Took eight months.", True, (30, 30, 42)),
            ("priya.n", "Sunrise class this morning.", True, (44, 34, 30)),
            ("sneha.k", "New PB on the leg press!", False, (28, 40, 36)),
            ("rahul.v", "Rack pulls before closing.", False, (40, 30, 34)),
        ]
        for handle, caption, approved, colour in specs:
            post = GalleryPost(
                uploader=members[handle],
                media_type=MediaType.IMAGE,
                caption=f"[demo] {caption}",
                approved=approved,
            )
            post.media.save(f"demo-{handle}.png", png(colour), save=False)
            post.save()

    def _devices(self, members):
        device = Device.objects.filter(serial="DEMO-DOOR-01").first()
        if device:
            return

        raw, hashed = generate_key()
        device = Device.objects.create(
            name="Front Door Terminal",
            serial="DEMO-DOOR-01",
            location="Reception",
            api_key_hash=hashed,
        )
        self._device_key = raw

        # A clean in/out pair, plus a punch from a finger nobody is enrolled
        # under -- that's the queue the admin works through.
        now = timezone.now()
        record_punch(device, "FP-1002", now - timedelta(hours=4))
        record_punch(device, "FP-1002", now - timedelta(hours=2))
        record_punch(device, "FP-8888", now - timedelta(hours=1))

        # A gate, so the demo shows a refusal as well as a recorded visit. The
        # terminal above never turns anyone away; this one does, and the two
        # sitting side by side is the whole point of the `kind` field.
        gate_raw, gate_hashed = generate_key()
        gate = Device.objects.create(
            name="Floor Turnstile",
            serial="DEMO-GATE-01",
            location="Gym floor entrance",
            api_key_hash=gate_hashed,
            kind=DeviceKind.TURNSTILE,
        )
        self._gate_key = gate_raw
        gate.last_seen_at = now - timedelta(minutes=20)
        gate.save(update_fields=["last_seen_at"])

        from devices.access import request_access

        # One of each answer the gate can give, so the refusal feed shows the
        # reasons rather than a single example. Deliberately not Arjun: he is
        # the member with a visit left open for the dashboard's live timer, and
        # a gate punch would close it.
        request_access(gate, "FP-1002", at=now - timedelta(minutes=25))  # let in
        request_access(gate, "FP-1003", at=now - timedelta(minutes=20))  # expired
        request_access(gate, "FP-1004", at=now - timedelta(minutes=12))  # on hold
        request_access(gate, "FP-7777", at=now - timedelta(minutes=6))   # unknown card

        # last_seen_at is normally stamped by the device-key authenticator on a
        # real HTTP call; seeding goes straight to the service, so set it here
        # rather than leave the panel reporting a terminal that never checked in.
        device.last_seen_at = now - timedelta(hours=1)
        device.save(update_fields=["last_seen_at"])

    def _enquiries(self, admin):
        if Enquiry.objects.exists():
            return
        specs = [
            # name, phone, days from today, status, source, note
            ("Deepak Joshi", "+91 98200 41001", 0, EnquiryStatus.OPEN,
             EnquirySource.WALK_IN, "Walked in, asked about monthly rates."),
            ("Fatima Sheikh", "+91 98200 41002", -2, EnquiryStatus.TRIAL,
             EnquirySource.INSTAGRAM, "Wants a trial class before joining."),
            ("Aditya Rane", "+91 98200 41003", -5, EnquiryStatus.OPEN,
             EnquirySource.PHONE, "Called about personal training."),
            ("Neha Bhatt", "+91 98200 41004", 3, EnquiryStatus.OPEN,
             EnquirySource.GOOGLE, "Comparing us with the place down the road."),
            ("Sanjay Gupta", "+91 98200 41005", -8, EnquiryStatus.CONTACTED,
             EnquirySource.INSTAGRAM, "Spoke on the phone, thinking it over."),
            ("Ritu Malhotra", "+91 98200 41006", -12, EnquiryStatus.LOST,
             EnquirySource.FACEBOOK, "Went with the place down the road."),
        ]
        trail = {
            "Sanjay Gupta": [
                "Rang once, no answer.",
                "Spoke for ten minutes -- wants to see the equipment first.",
            ],
            "Fatima Sheikh": ["Booked her into Saturday's 7am class."],
        }
        for name, phone, offset, status, source, note in specs:
            enquiry = Enquiry.objects.create(
                name=name,
                phone=phone,
                follow_up_on=TODAY + timedelta(days=offset),
                status=status,
                source=source,
                notes=note,
                last_contacted_on=TODAY + timedelta(days=offset) if status != EnquiryStatus.OPEN else None,
                created_by=admin,
            )
            for body in trail.get(name, []):
                EnquiryNote.objects.create(enquiry=enquiry, body=body, author=admin)

    # ----------------------------------------------------------- day passes

    def _day_passes(self, admin):
        """A few walk-ins, one of them currently in the building.

        Their visits go in the same table as everyone else's, so the occupancy
        figures count them -- which is the whole reason a guest is not given a
        stub member account.
        """
        if DayPass.objects.exists():
            return
        from attendance.services import toggle_guest_visit

        specs = [
            # name, phone, days ago, amount, still inside
            ("Karan Mehta", "+91 98200 51001", 0, "300", True),
            ("Anita Shah", "+91 98200 51002", 0, "300", False),
            ("Vivek Nair", "+91 98200 51003", 1, "300", False),
            ("Tanvi Rao", "+91 98200 51004", 3, "250", False),
        ]
        for name, phone, days_ago, amount, inside in specs:
            day = TODAY - timedelta(days=days_ago)
            day_pass = DayPass.objects.create(
                name=name,
                phone=phone,
                valid_on=day,
                amount=Decimal(amount),
                method=PaymentMethod.UPI,
                notes="[demo] Seeded walk-in.",
                issued_by=admin,
            )
            # Only today's passes can be toggled through the service, which
            # stamps `check_in_time` itself; older ones get their visit written
            # directly so the day is right.
            if days_ago == 0:
                record, _ = toggle_guest_visit(day_pass)
                if not inside:
                    toggle_guest_visit(day_pass)
            else:
                start = timezone.localtime().replace(
                    hour=11, minute=0, second=0, microsecond=0
                ) - timedelta(days=days_ago)
                record = CheckInOut.objects.create(day_pass=day_pass)
                CheckInOut.objects.filter(pk=record.pk).update(
                    check_in_time=start, check_out_time=start + timedelta(minutes=70)
                )

    # ---------------------------------------------------------------- rota

    def _shifts(self, admin, trainers):
        """A fortnight of rota, so the week view has something either side of
        today and "on the floor now" is not empty when the demo is opened."""
        if Shift.objects.exists():
            return

        ravi, meera = trainers[0][0], trainers[1][0]
        # weekday offset from Monday -> (staff, start hour, end hour, position)
        pattern = [
            (ravi, 6, 14, Position.FLOOR),
            (meera, 14, 22, Position.FLOOR),
            (admin, 9, 18, Position.FRONT_DESK),
        ]

        monday = TODAY - timedelta(days=TODAY.weekday())
        for week in (0, 1):
            for offset in range(7):
                day = monday + timedelta(days=week * 7 + offset)
                # Sunday is a short day, with only the desk covered.
                roster = pattern[-1:] if day.weekday() == 6 else pattern
                for staff, start, end, position in roster:
                    Shift.objects.create(
                        staff=staff,
                        date=day,
                        start_time=time(start, 0),
                        end_time=time(end, 0),
                        position=position,
                        created_by=admin,
                    )

    # ------------------------------------------------------- personal training

    def _pt(self, members, trainers):
        """Trainer hours, a day off, and a few one-to-one bookings.

        Slots are never seeded -- they are derived from these windows, so the
        demo exercises the real derivation rather than a table of fake slots.
        """
        if Availability.objects.exists():
            return
        from pt.services import BookingError, book_session

        ravi, meera = trainers[0][0], trainers[1][0]
        pattern = {
            ravi: [(0, 6, 10), (2, 6, 10), (4, 6, 10)],
            meera: [(1, 15, 19), (3, 15, 19), (5, 8, 12)],
        }
        for trainer, windows in pattern.items():
            for weekday, start, end in windows:
                Availability.objects.create(
                    trainer=trainer,
                    weekday=weekday,
                    start_time=time(start, 0),
                    end_time=time(end, 0),
                )

        # One day off, so the "pattern survives a holiday" behaviour is visible.
        Unavailable.objects.create(
            trainer=ravi, date=TODAY + timedelta(days=9), reason="[demo] Away"
        )

        # A few completed sessions behind us, so PT utilisation on the owner
        # dashboard has something to report for the window it looks at. These
        # are written directly rather than booked: the booking service refuses
        # a date in the past, correctly.
        from pt.models import SessionStatus

        past = [
            (ravi, members["arjun.s"], 0, 7),
            (ravi, members["arjun.s"], 2, 8),
            (meera, members["priya.n"], 1, 16),
            (meera, members["sneha.k"], 3, 17),
            (ravi, members["meena.d"], 4, 9),
        ]
        for trainer, member, weekday, hour in past:
            day = TODAY - timedelta(days=1)
            while day.weekday() != weekday:
                day -= timedelta(days=1)
            PTSession.objects.get_or_create(
                trainer=trainer,
                date=day,
                start_time=time(hour, 0),
                defaults={
                    "member": member,
                    "end_time": time(hour + 1, 0),
                    "status": SessionStatus.COMPLETED,
                    "price": Decimal("800"),
                    "is_paid": True,
                },
            )

        # Book a handful of the next fortnight's slots.
        wanted = [
            (ravi, members["arjun.s"], 0, 7),
            (ravi, members["rahul.v"], 2, 8),
            (meera, members["priya.n"], 1, 16),
            (meera, members["meena.d"], 3, 17),
        ]
        for trainer, member, weekday, hour in wanted:
            day = TODAY + timedelta(days=1)
            while day.weekday() != weekday:
                day += timedelta(days=1)
            try:
                book_session(
                    trainer=trainer,
                    member=member,
                    on=day,
                    start_time=time(hour, 0),
                    end_time=time(hour + 1, 0),
                    price=Decimal("800"),
                    booked_by=member,
                )
            except BookingError:
                # A slot that doesn't line up with the pattern is skipped
                # rather than faked into existence.
                continue

    def _feedback(self, members):
        """A live post-visit survey plus a spread of answers.

        Scores are picked to give a positive but not perfect NPS, so the
        dashboard shows the bands doing real work rather than a wall of tens.
        Each answer is tied to the visit that prompted it, which is what makes
        the "already answered" check derived rather than a flag.
        """
        if Survey.objects.exists():
            return

        survey = Survey.objects.create(
            title="[demo] After your session",
            question="How likely are you to recommend us to a friend?",
            trigger=Trigger.POST_CHECKIN,
            cooldown_days=90,
        )

        # Spread across the last few months so the trend chart has a shape.
        # Arjun's sits outside the 90-day cooldown on purpose: he is the
        # account you log in as to see the member side, and with everyone
        # inside the cooldown the prompt would correctly render nothing.
        answers = [
            ("arjun.s", 10, "Best squat rack in the city.", 200),
            ("priya.n", 9, "", 3),
            ("rahul.v", 6, "Showers are cold in the morning.", 70),
            ("sneha.k", 8, "", 20),
            ("meena.d", 4, "Too crowded at 7pm, had to wait for a bench.", 3),
            ("vikram.r", 9, "Signing up took two minutes.", 45),
        ]
        for handle, score, comment, days_ago in answers:
            member = members.get(handle)
            if member is None:
                continue
            # The occasion this answer belongs to: their most recent finished
            # visit. Without one the response is still valid, just untied.
            visit = (
                CheckInOut.objects.filter(user=member, check_out_time__isnull=False)
                .order_by("-check_in_time")
                .first()
            )
            answer = SurveyResponse.objects.create(
                survey=survey, member=member, score=score, comment=comment, visit=visit
            )
            SurveyResponse.objects.filter(pk=answer.pk).update(
                created_at=timezone.now() - timedelta(days=days_ago)
            )

    def _referrals(self, members, admin):
        """One referral at each stage, so the admin queue has something in it.

        The reward is granted through the real service, which writes a
        zero-amount payment -- the referrer's expiry moves for the same reason
        a renewal moves it.
        """
        if Referral.objects.exists():
            return
        ReferralProgram.objects.create(
            reward_days=15, blurb="[demo] Bring a friend, train 15 days on us."
        )

        arjun, priya = members["arjun.s"], members["priya.n"]
        # Codes are minted on first use, so ask for them the way the app does.
        code_for(arjun)
        code_for(priya)

        # Never signed up: still sitting in the call-back queue.
        Referral.objects.create(
            referrer=arjun,
            name="Karan Mehta",
            phone="+91 98200 42001",
            notes="[demo] Gym buddy from work.",
        )
        # Signed up but hasn't paid yet.
        Referral.objects.create(
            referrer=arjun,
            name="Vikram Reddy",
            phone="+91 98200 42002",
            referred_user=members["vikram.r"],
            notes="[demo] Walked in on Arjun's code.",
        )
        # Joined and paid -- this one is owed a reward.
        joined = Referral.objects.create(
            referrer=priya,
            name="Sneha Kulkarni",
            phone="+91 98200 42003",
            referred_user=members["sneha.k"],
            notes="[demo] Signed up after a trial class.",
        )
        # And one already paid out, so the member page shows earned days.
        paid = Referral.objects.create(
            referrer=arjun,
            name="Rahul Verma",
            phone="+91 98200 42004",
            referred_user=members["rahul.v"],
            notes="[demo] Referred last quarter.",
        )
        grant_reward(paid, granted_by=admin, notes="[demo] Seeded reward.")
        # `joined` is deliberately left unrewarded so the admin queue isn't empty.
        assert joined.is_rewardable

    # ---------------------------------------------------------------- report

    def _report(self, admin, trainers, members):
        line = "=" * 66
        out = self.stdout
        out.write("")
        out.write(self.style.SUCCESS(line))
        out.write(self.style.SUCCESS("  IRONCORE demo data seeded"))
        out.write(self.style.SUCCESS(line))
        out.write("")
        out.write(f"  Every account below uses the password:  {PASSWORD}")
        out.write(f"  ...and two-step sign-in with the authenticator key:  {DEMO_MFA_SECRET}")
        out.write("  Add that key to any authenticator app once, or open this on a phone:")
        out.write(f"    {mfa.provisioning_uri(DEMO_MFA_SECRET, 'demo accounts')}")
        out.write("")

        out.write(self.style.MIGRATE_HEADING("  ADMIN"))
        out.write(f"    demo.admin          {admin.get_full_name()} -- full admin portal")
        out.write("")

        out.write(self.style.MIGRATE_HEADING("  TRAINERS"))
        for user, specialty in trainers:
            roster = user.assigned_members.count()
            out.write(
                f"    {user.username:<20}{user.get_full_name()} -- {specialty}, "
                f"{roster} assigned member(s)"
            )
        out.write("")

        out.write(self.style.MIGRATE_HEADING("  MEMBERS"))
        notes = {
            "arjun.s": "richest data: 8 weeks of lifts, weigh-ins, live goal, open check-in",
            "priya.n": "yoga member, achieved goal, class bookings",
            "rahul.v": "lapsed payment, so the ledger derives 'expired'",
            "sneha.k": "on hold -- the one status an admin sets by hand",
            "vikram.r": "brand new: empty states everywhere, no payment on file yet",
            "meena.d": "stopped coming a week ago -- the retention list's cooling band",
        }
        for handle, user in members.items():
            # Re-read: several statuses are set by queryset .update(), which
            # leaves the in-memory profile stale.
            status = MemberProfile.objects.get(user=user).membership_status
            out.write(f"    {handle:<20}{user.get_full_name():<18}[{status}] {notes[handle]}")
        out.write("")

        key = getattr(self, "_device_key", None)
        if key:
            out.write(self.style.MIGRATE_HEADING("  DEVICES"))
            out.write(f"    terminal  X-Device-Key: {key}")
            gate_key = getattr(self, "_gate_key", None)
            if gate_key:
                out.write(f"    turnstile X-Device-Key: {gate_key}")
            out.write("    (shown once -- rotate from Admin > Devices if lost)")
            out.write("")

        out.write(self.style.MIGRATE_HEADING("  COUNTS"))
        out.write(f"    exercises {Exercise.objects.count():>4}   "
                  f"check-ins {CheckInOut.objects.count():>4}   "
                  f"workout sets {WorkoutLog.objects.count():>4}")
        out.write(f"    weigh-ins {BodyMeasurement.objects.count():>4}   "
                  f"payments  {sum(m.payments.count() for m in members.values()):>4}   "
                  f"classes      {ClassSession.objects.count():>4}")
        out.write(f"    offers    {Discount.objects.count():>4}   "
                  f"invoices  {Invoice.objects.count():>4}   "
                  f"expenses     {Expense.objects.count():>4}")
        out.write(f"    foods     {FoodItem.objects.count():>4}   "
                  f"diet days {DietDay.objects.count():>4}   "
                  f"meal items   {DietMealItem.objects.count():>4}")
        out.write(f"    referrals {Referral.objects.count():>4}   "
                  f"enquiries {Enquiry.objects.count():>4}")
        out.write(f"    badges    {Badge.objects.count():>4}   "
                  f"awarded   {MemberBadge.objects.count():>4}   "
                  f"records      {PersonalRecord.objects.count():>4}")
        out.write(f"    shifts    {Shift.objects.count():>4}   "
                  f"day passes {DayPass.objects.count():>3}   "
                  f"pt sessions {PTSession.objects.count():>4}")
        out.write("")
        out.write("  Reset with:  python manage.py seed_demo --wipe")
        out.write(self.style.SUCCESS(line))
