"""The per-organisation and per-tenant uniqueness rules, asserted.

Four constraints were rewritten from platform-wide singletons to per-gym rules
during the tenancy migration, and nothing tested them afterwards. A rule with no
test can stop holding silently -- and these are exactly the rules that made
multi-tenancy impossible before they were changed, so a regression would take
the platform back to one gym without anything failing.

Each is checked in both directions, which is the point: the *same* gym cannot
have two, and a *different* gym is unaffected. Only asserting the first half
would pass just as happily if the constraint had never been scoped at all.

Kept in `tenancy` rather than in each app because the rule under test is a
tenancy rule; the app the row happens to live in is incidental.

A `NullOrganisationTests` group used to sit at the bottom, documenting that
these rules could not fire while the FKs were nullable. It carried an assertion
that failed the moment the columns became NOT NULL, telling whoever saw it to
delete the group -- which is what happened, and why it is gone.
"""

from datetime import date
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from crm.models import RetentionPolicy
from expenses.models import ExpenseCategory
from invoicing.models import InvoiceCounter
from referrals.models import ReferralProgram

from .models import Organisation, Tenant


def make_org(slug):
    return Organisation.objects.create(name=slug.title(), slug=slug)


def make_tenant(org, slug):
    return Tenant.objects.create(organisation=org, name=slug.title(), slug=slug)


class TwoGymsSetup(TestCase):
    """Two unrelated gyms, which is the situation every rule below is about.

    Reads go through `.unscoped` on purpose. These assertions are *about* two
    organisations at once, so pretending to be inside one of them would hide
    exactly what is being checked -- and rows are created with an explicit
    organisation, which the stamping signal leaves alone.
    """

    @classmethod
    def setUpTestData(cls):
        cls.one = make_org("gym-one")
        cls.two = make_org("gym-two")
        cls.one_main = make_tenant(cls.one, "gym-one-main")
        cls.two_main = make_tenant(cls.two, "gym-two-main")


class InvoiceCounterTests(TwoGymsSetup):
    """`one_counter_per_tenant_per_year`.

    The most consequential of the four. Keyed on the year alone, two gyms drew
    from a single sequence -- so each gym's own run of invoice numbers came out
    full of holes, and a gapless statutory sequence is the entire reason this
    table exists. A burnt number cannot be recovered afterwards.
    """

    def test_one_branch_cannot_hold_two_counters_for_a_year(self):
        InvoiceCounter.unscoped.create(tenant=self.one_main, financial_year="2025-26")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                InvoiceCounter.unscoped.create(
                    tenant=self.one_main, financial_year="2025-26"
                )

    def test_but_another_branch_keeps_its_own(self):
        InvoiceCounter.unscoped.create(tenant=self.one_main, financial_year="2025-26")
        InvoiceCounter.unscoped.create(tenant=self.two_main, financial_year="2025-26")
        self.assertEqual(InvoiceCounter.unscoped.count(), 2)

    def test_the_same_branch_may_hold_one_per_year(self):
        InvoiceCounter.unscoped.create(tenant=self.one_main, financial_year="2025-26")
        InvoiceCounter.unscoped.create(tenant=self.one_main, financial_year="2026-27")
        self.assertEqual(InvoiceCounter.unscoped.filter(tenant=self.one_main).count(), 2)

    def test_two_branches_allocate_independent_sequences(self):
        """The behaviour the constraint exists to protect, end to end."""
        day = date(2025, 6, 1)
        first = [InvoiceCounter.next_for(self.one_main, day)[1] for _ in range(3)]
        second = [InvoiceCounter.next_for(self.two_main, day)[1] for _ in range(2)]

        self.assertEqual(first, [1, 2, 3])
        self.assertEqual(second, [1, 2])


class RetentionPolicyTests(TwoGymsSetup):
    """`one_active_retention_policy_per_organisation`."""

    def test_one_organisation_cannot_have_two_live_policies(self):
        RetentionPolicy.unscoped.create(organisation=self.one, quiet_days=10, cooling_days=5)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                RetentionPolicy.unscoped.create(
                    organisation=self.one, quiet_days=14, cooling_days=7
                )

    def test_but_another_organisation_sets_its_own_thresholds(self):
        RetentionPolicy.unscoped.create(organisation=self.one, quiet_days=10, cooling_days=5)
        RetentionPolicy.unscoped.create(organisation=self.two, quiet_days=21, cooling_days=9)
        self.assertEqual(RetentionPolicy.unscoped.filter(is_active=True).count(), 2)

    def test_a_retired_policy_does_not_block_a_new_one(self):
        RetentionPolicy.unscoped.create(
            organisation=self.one, quiet_days=10, cooling_days=5, is_active=False
        )
        RetentionPolicy.unscoped.create(organisation=self.one, quiet_days=14, cooling_days=7)
        self.assertEqual(RetentionPolicy.unscoped.filter(organisation=self.one).count(), 2)


class ReferralProgramTests(TwoGymsSetup):
    """`one_active_referral_program_per_organisation`."""

    def test_one_organisation_cannot_run_two_live_programmes(self):
        ReferralProgram.unscoped.create(organisation=self.one, reward_days=7)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ReferralProgram.unscoped.create(organisation=self.one, reward_days=14)

    def test_but_another_organisation_runs_its_own(self):
        ReferralProgram.unscoped.create(organisation=self.one, reward_days=7)
        ReferralProgram.unscoped.create(organisation=self.two, reward_days=30)
        self.assertEqual(ReferralProgram.unscoped.filter(is_active=True).count(), 2)

    def test_a_switched_off_programme_does_not_block_a_new_one(self):
        ReferralProgram.unscoped.create(
            organisation=self.one, reward_days=7, is_active=False
        )
        ReferralProgram.unscoped.create(organisation=self.one, reward_days=14)
        self.assertEqual(ReferralProgram.unscoped.filter(organisation=self.one).count(), 2)


class ExpenseCategoryTests(TwoGymsSetup):
    """`one_expense_category_per_organisation`.

    "Rent" is the obvious category name for every gym on the platform, so a
    globally unique name meant the second gym to add it was refused.
    """

    def test_one_organisation_cannot_have_two_categories_named_the_same(self):
        ExpenseCategory.unscoped.create(organisation=self.one, name="Rent")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ExpenseCategory.unscoped.create(organisation=self.one, name="Rent")

    def test_but_two_gyms_may_both_have_rent(self):
        ExpenseCategory.unscoped.create(organisation=self.one, name="Rent")
        ExpenseCategory.unscoped.create(organisation=self.two, name="Rent")
        self.assertEqual(ExpenseCategory.unscoped.filter(name="Rent").count(), 2)

    def test_one_organisation_may_have_many_different_categories(self):
        for name in ("Rent", "Equipment", "Salaries"):
            ExpenseCategory.unscoped.create(organisation=self.one, name=name)
        self.assertEqual(ExpenseCategory.unscoped.filter(organisation=self.one).count(), 3)
