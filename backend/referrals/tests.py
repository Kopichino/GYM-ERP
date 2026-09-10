from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from core.testing import TenantAPIMixin

from accounts.models import MemberProfile, MembershipStatus, Role
from billing.models import PaymentMethod, PaymentStatus, Plan
from billing.services import record_payment

from .models import Referral, ReferralProgram, ReferralReward, ReferralStatus
from .services import ReferralError, claim, code_for, grant_reward, resolve_code

User = get_user_model()


def make_member(username, **kwargs):
    user = User.objects.create_user(
        username=username, email=f"{username}@example.com", password="pass12345", **kwargs
    )
    MemberProfile.objects.get_or_create(user=user)
    return user


class ReferralCodeTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.member = make_member("coder")

    def test_code_is_minted_once_and_reused(self):
        first = code_for(self.member)
        self.assertTrue(first)
        self.assertEqual(code_for(self.member), first)

    def test_code_avoids_characters_that_get_misread(self):
        code = code_for(self.member)
        for confusable in "O0I1":
            self.assertNotIn(confusable, code)

    def test_resolve_forgives_case_spaces_and_dashes(self):
        code = code_for(self.member)
        spaced = f" {code[:3]}-{code[3:].lower()} "
        self.assertEqual(resolve_code(spaced), self.member)

    def test_unknown_code_resolves_to_nobody(self):
        self.assertIsNone(resolve_code("ZZZZZZ"))
        self.assertIsNone(resolve_code(""))


class ClaimTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.referrer = make_member("sponsor")
        self.code = code_for(self.referrer)

    def test_signup_with_a_code_records_the_referral(self):
        resp = self.client.post(
            "/api/auth/signup/",
            {
                "username": "newjoiner",
                "email": "nj@example.com",
                "password": "SomeStrongPass123",
                "referral_code": self.code,
            },
        )
        self.assertEqual(resp.status_code, 201)
        referral = Referral.objects.get(referrer=self.referrer)
        self.assertEqual(referral.referred_user.username, "newjoiner")
        self.assertEqual(referral.status, ReferralStatus.SIGNED_UP)

    def test_a_bad_code_never_blocks_a_signup(self):
        resp = self.client.post(
            "/api/auth/signup/",
            {
                "username": "unlucky",
                "email": "u@example.com",
                "password": "SomeStrongPass123",
                "referral_code": "NOPE99",
            },
        )
        self.assertEqual(resp.status_code, 201)
        self.assertFalse(Referral.objects.exists())

    def test_a_pending_referral_is_completed_rather_than_duplicated(self):
        Referral.objects.create(referrer=self.referrer, name="Jane Doe", phone="+91 90000 00001")
        joiner = make_member("janed", first_name="Jane", last_name="Doe")
        referral = claim(self.code, joiner)
        self.assertEqual(Referral.objects.count(), 1)
        self.assertEqual(referral.referred_user, joiner)

    def test_you_cannot_refer_yourself(self):
        self.assertIsNone(claim(self.code, self.referrer))


class ReferralStatusTests(TenantAPIMixin, APITestCase):
    """Status is read off the ledger, so it moves on its own."""

    def setUp(self):
        self.referrer = make_member("host")
        self.joiner = make_member("guest")
        self.plan = Plan.objects.create(name="Monthly", price=Decimal("1500"), duration_days=30)
        self.referral = Referral.objects.create(referrer=self.referrer, name="Guest")

    def test_pending_until_they_have_an_account(self):
        self.assertEqual(self.referral.status, ReferralStatus.PENDING)

    def test_signed_up_until_they_pay(self):
        self.referral.referred_user = self.joiner
        self.referral.save()
        self.assertEqual(self.referral.status, ReferralStatus.SIGNED_UP)

    def test_joined_once_a_completed_payment_lands(self):
        self.referral.referred_user = self.joiner
        self.referral.save()
        record_payment(
            member=self.joiner,
            plan=self.plan,
            amount=self.plan.price,
            method=PaymentMethod.CASH,
        )
        self.assertEqual(self.referral.status, ReferralStatus.JOINED)
        self.assertTrue(self.referral.is_rewardable)

    def test_a_refund_walks_the_status_back(self):
        self.referral.referred_user = self.joiner
        self.referral.save()
        payment = record_payment(
            member=self.joiner,
            plan=self.plan,
            amount=self.plan.price,
            method=PaymentMethod.CASH,
        )
        payment.status = PaymentStatus.REFUNDED
        payment.save(update_fields=["status"])
        self.assertEqual(self.referral.status, ReferralStatus.SIGNED_UP)


class RewardTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.admin = make_member("rewardadmin", role=Role.ADMIN)
        self.referrer = make_member("giver")
        self.joiner = make_member("taker")
        self.plan = Plan.objects.create(name="Monthly", price=Decimal("1500"), duration_days=30)
        ReferralProgram.objects.create(reward_days=15, blurb="Bring a friend.")
        self.referral = Referral.objects.create(
            referrer=self.referrer, name="Taker", referred_user=self.joiner
        )
        # The referrer is a paying member; the person they brought has paid too.
        self.referrer_payment = record_payment(
            member=self.referrer, plan=self.plan, amount=self.plan.price, method=PaymentMethod.CASH
        )
        record_payment(
            member=self.joiner, plan=self.plan, amount=self.plan.price, method=PaymentMethod.CASH
        )

    def test_reward_extends_the_referrer_through_the_billing_ledger(self):
        before = self.referrer_payment.period_end
        reward = grant_reward(self.referral, granted_by=self.admin)
        self.assertEqual(reward.days_granted, 15)
        # The free days arrive as a real, zero-amount payment stacked on top.
        self.assertEqual(reward.payment.amount, Decimal("0.00"))
        self.assertEqual(reward.payment.period_start, before)
        self.assertEqual((reward.payment.period_end - before).days, 15)

    def test_reward_keeps_the_derived_status_correct(self):
        grant_reward(self.referral, granted_by=self.admin)
        self.referrer.profile.refresh_from_db()
        self.assertEqual(self.referrer.profile.membership_status, MembershipStatus.ACTIVE)

    def test_cannot_reward_twice(self):
        grant_reward(self.referral, granted_by=self.admin)
        with self.assertRaises(ReferralError):
            grant_reward(self.referral, granted_by=self.admin)

    def test_cannot_reward_a_referral_that_has_not_paid(self):
        unpaid = Referral.objects.create(referrer=self.referrer, name="Nobody")
        with self.assertRaises(ReferralError):
            grant_reward(unpaid, granted_by=self.admin)

    def test_cannot_reward_a_referrer_with_no_plan_on_file(self):
        stranger = make_member("noplan")
        buyer = make_member("buyer")
        record_payment(
            member=buyer, plan=self.plan, amount=self.plan.price, method=PaymentMethod.CASH
        )
        referral = Referral.objects.create(
            referrer=stranger, name="Buyer", referred_user=buyer
        )
        with self.assertRaises(ReferralError):
            grant_reward(referral, granted_by=self.admin)


class ReferralApiTests(TenantAPIMixin, APITestCase):
    def setUp(self):
        self.admin = make_member("apiadmin", role=Role.ADMIN)
        self.member = make_member("apimember")
        self.other = make_member("apiother")
        ReferralProgram.objects.create(reward_days=10, blurb="Ten days on us.")

    def test_member_raises_a_referral_and_it_joins_the_call_back_queue(self):
        self.client.force_authenticate(self.member)
        resp = self.client.post(
            "/api/referrals/", {"name": "Ravi Menon", "phone": "+91 90000 12345"}
        )
        self.assertEqual(resp.status_code, 201)
        referral = Referral.objects.get(pk=resp.data["id"])
        self.assertEqual(referral.referrer, self.member)
        self.assertIsNotNone(referral.enquiry)
        self.assertEqual(referral.enquiry.follow_up_on, timezone.localdate())

    def test_a_referral_without_a_phone_raises_no_enquiry(self):
        self.client.force_authenticate(self.member)
        resp = self.client.post("/api/referrals/", {"name": "No Phone"})
        self.assertEqual(resp.status_code, 201)
        self.assertIsNone(Referral.objects.get(pk=resp.data["id"]).enquiry)

    def test_member_sees_only_their_own_referrals(self):
        Referral.objects.create(referrer=self.other, name="Theirs")
        mine = Referral.objects.create(referrer=self.member, name="Mine")
        self.client.force_authenticate(self.member)
        resp = self.client.get("/api/referrals/")
        self.assertEqual([row["id"] for row in resp.data["results"]], [mine.id])

    def test_mine_returns_the_code_and_the_offer(self):
        self.client.force_authenticate(self.member)
        resp = self.client.get("/api/referrals/mine/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["code"])
        self.assertEqual(resp.data["reward_days"], 10)
        self.assertEqual(resp.data["blurb"], "Ten days on us.")
        self.assertEqual(resp.data["total_referred"], 0)

    def test_members_cannot_reward_themselves(self):
        referral = Referral.objects.create(referrer=self.member, name="X")
        self.client.force_authenticate(self.member)
        resp = self.client.post(f"/api/referrals/{referral.id}/reward/")
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(ReferralReward.objects.exists())

    def test_rewarding_an_ineligible_referral_explains_why(self):
        referral = Referral.objects.create(referrer=self.member, name="Not joined")
        self.client.force_authenticate(self.admin)
        resp = self.client.post(f"/api/referrals/{referral.id}/reward/")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("hasn't joined", resp.data["detail"])

    def test_only_admins_change_the_programme(self):
        self.client.force_authenticate(self.member)
        self.assertEqual(
            self.client.post("/api/referrals/programs/", {"reward_days": 90}).status_code, 403
        )

    def test_creating_a_programme_retires_the_previous_one(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post("/api/referrals/programs/", {"reward_days": 30})
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(ReferralProgram.objects.filter(is_active=True).count(), 1)
        self.assertEqual(ReferralProgram.current().reward_days, 30)
