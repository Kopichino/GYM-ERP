"""The tenancy core: organisations, branches, memberships, and scope."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from accounts.models import Role

from . import context
from .models import Membership, Organisation, Tenant

User = get_user_model()
TODAY = timezone.localdate()


def make_org(slug="fitzone", name="FitZone"):
    return Organisation.objects.create(name=name, slug=slug)


def make_tenant(org, slug, name=None):
    return Tenant.objects.create(
        organisation=org, slug=slug, name=name or slug.title()
    )


def make_user(username, role=Role.MEMBER):
    return User.objects.create_user(
        username=username, email=f"{username}@example.com", password="pass12345", role=role
    )


class HierarchyTests(TestCase):
    def setUp(self):
        self.org = make_org()

    def test_one_organisation_owns_many_branches(self):
        make_tenant(self.org, "central")
        make_tenant(self.org, "north")
        self.assertEqual(self.org.tenants.count(), 2)

    def test_branch_slugs_are_globally_unique_not_per_organisation(self):
        """They become hostnames, and hostnames are a global namespace."""
        other = make_org(slug="ironworks", name="Ironworks")
        make_tenant(self.org, "central")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                make_tenant(other, "central")

    def test_an_organisation_cannot_be_deleted_out_from_under_its_branches(self):
        make_tenant(self.org, "central")
        from django.db.models import ProtectedError

        with self.assertRaises(ProtectedError):
            self.org.delete()

    def test_a_single_site_gym_is_just_an_organisation_with_one_branch(self):
        """No special case: one code path whether there are one or ten."""
        tenant = make_tenant(self.org, "only")
        self.assertEqual(list(self.org.tenants.all()), [tenant])


class MembershipTests(TestCase):
    def setUp(self):
        self.org = make_org()
        self.central = make_tenant(self.org, "central")
        self.north = make_tenant(self.org, "north")
        self.user = make_user("ravi")

    def test_one_person_can_hold_two_roles_at_one_branch(self):
        """A trainer who also trains there. The PT diary already assumes this."""
        Membership.objects.create(user=self.user, tenant=self.central, role=Role.TRAINER)
        Membership.objects.create(user=self.user, tenant=self.central, role=Role.MEMBER)
        self.assertEqual(self.user.memberships.count(), 2)

    def test_but_not_the_same_role_twice(self):
        Membership.objects.create(user=self.user, tenant=self.central, role=Role.TRAINER)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Membership.objects.create(
                    user=self.user, tenant=self.central, role=Role.TRAINER
                )

    def test_a_trainer_can_work_at_two_unrelated_gyms(self):
        """The whole reason role is not a column on User."""
        other = make_tenant(make_org(slug="ironworks", name="Ironworks"), "ironworks-hq")
        Membership.objects.create(user=self.user, tenant=self.central, role=Role.TRAINER)
        Membership.objects.create(user=self.user, tenant=other, role=Role.TRAINER)
        self.assertEqual(self.user.memberships.count(), 2)

    def test_an_owner_holds_admin_at_every_branch(self):
        for tenant in (self.central, self.north):
            Membership.objects.create(user=self.user, tenant=tenant, role=Role.ADMIN)
        self.assertEqual(
            set(self.user.memberships.values_list("tenant__slug", flat=True)),
            {"central", "north"},
        )

    def test_an_open_ended_membership_is_current(self):
        row = Membership.objects.create(
            user=self.user, tenant=self.central, role=Role.MEMBER
        )
        self.assertTrue(row.is_current())

    def test_a_dated_one_lapses(self):
        """How a day-pass guest who wanted their history is represented."""
        row = Membership.objects.create(
            user=self.user, tenant=self.central, role=Role.MEMBER,
            starts_on=TODAY - timedelta(days=10), expires_on=TODAY - timedelta(days=1),
        )
        self.assertFalse(row.is_current())

    def test_it_is_current_on_its_last_day(self):
        row = Membership.objects.create(
            user=self.user, tenant=self.central, role=Role.MEMBER, expires_on=TODAY
        )
        self.assertTrue(row.is_current())

    def test_one_that_has_not_started_is_not_current(self):
        row = Membership.objects.create(
            user=self.user, tenant=self.central, role=Role.MEMBER,
            starts_on=TODAY + timedelta(days=3),
        )
        self.assertFalse(row.is_current())

    def test_deactivating_revokes_access_without_touching_the_dates(self):
        row = Membership.objects.create(
            user=self.user, tenant=self.central, role=Role.ADMIN, is_active=False
        )
        self.assertFalse(row.is_current())
        self.assertIsNone(row.expires_on)

    def test_it_cannot_expire_before_it_starts(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Membership.objects.create(
                    user=self.user, tenant=self.central, role=Role.MEMBER,
                    starts_on=TODAY, expires_on=TODAY - timedelta(days=1),
                )


class ScopeTests(TestCase):
    """`context` fails closed -- that is the whole point of it."""

    def setUp(self):
        self.org = make_org()
        self.tenant = make_tenant(self.org, "central")

    def test_requiring_a_tenant_with_none_set_is_an_error_not_a_default(self):
        with self.assertRaises(context.TenantScopeError):
            context.require()

    def test_inside_a_scope_it_is_the_tenant(self):
        with context.scope(self.tenant):
            self.assertEqual(context.require(), self.tenant)

    def test_the_previous_scope_is_restored_on_the_way_out(self):
        other = make_tenant(self.org, "north")
        with context.scope(self.tenant):
            with context.scope(other):
                self.assertEqual(context.require(), other)
            self.assertEqual(context.require(), self.tenant)

    def test_it_is_restored_even_when_the_block_raises(self):
        with context.scope(self.tenant):
            with self.assertRaises(ValueError):
                with context.scope(make_tenant(self.org, "north")):
                    raise ValueError("boom")
            self.assertEqual(context.require(), self.tenant)

    def test_platform_scope_is_not_a_tenant(self):
        """Deliberately no gym is different from nobody having said yet."""
        with context.platform_scope():
            self.assertTrue(context.is_platform())
            self.assertIsNone(context.get())
            with self.assertRaises(context.TenantScopeError):
                context.require()

    def test_get_returns_none_outside_any_scope(self):
        self.assertIsNone(context.get())
