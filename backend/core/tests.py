"""Direct tests for the shared permission and scoping helpers.

Every app in the project leans on these ~70 lines to decide who may read and
write what, but until now they were only ever exercised sideways, through
whichever app happened to mount them. A regression here would surface as a
puzzling 403 (or, far worse, a silent data leak) in an app that never changed,
so the rules get tested on their own terms as well.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework.permissions import BasePermission
from rest_framework.test import APIRequestFactory, APITestCase

from core.testing import TenantAPIMixin
from rest_framework.views import APIView

from accounts.models import MemberProfile, Role
from bodystats.models import BodyMeasurement
from core.permissions import (
    IsAdmin,
    IsAdminOrReadOnly,
    IsOwnerOrAdmin,
    IsTrainer,
    IsTrainerOrAdmin,
)
from core.scoping import may_write_for, visible_rows

User = get_user_model()


def make_user(username, role=Role.MEMBER, trainer=None):
    user = User.objects.create_user(
        username=username, email=f"{username}@example.com", password="pass12345", role=role
    )
    if role == Role.MEMBER:
        MemberProfile.objects.update_or_create(user=user, defaults={"trainer": trainer})
    user.refresh_from_db()
    return user


class PermissionClassTests(TenantAPIMixin, APITestCase):
    """Each class is asked directly, rather than through a mounted view, so a
    failure names the rule that broke instead of the endpoint that noticed."""

    @classmethod
    def setUpTestData(cls):
        cls.member = make_user("perm_member")
        cls.trainer = make_user("perm_trainer", role=Role.TRAINER)
        cls.admin = make_user("perm_admin", role=Role.ADMIN)

    def setUp(self):
        self.factory = APIRequestFactory()

    def _allows(self, permission, user, method="get"):
        """Ask one permission class directly.

        `APIRequestFactory` builds a request that never passes through the
        tenant middleware, so `request.access` has to be attached by hand --
        exactly what the middleware would have resolved from Membership. A
        request without it is refused by every class, which is the correct
        fail-closed default and is what `test_an_unresolved_request_is_refused`
        below pins.
        """
        from tenancy.resolution import access_for

        request = getattr(self.factory, method)("/")
        request.user = user
        request.access = access_for(user, self.tenant)
        return bool(permission().has_permission(request, APIView()))

    def test_an_unresolved_request_is_refused_by_every_class(self):
        """No middleware, no tenant, no roles -- so no.

        This is what makes a cross-tenant call safe without each view having to
        remember to check: a caller with no standing here looks exactly like a
        caller nobody resolved.
        """
        request = self.factory.get("/")
        request.user = self.admin
        for permission in (IsAdmin, IsTrainer, IsTrainerOrAdmin):
            self.assertFalse(
                bool(permission().has_permission(request, APIView())),
                permission.__name__,
            )

    def test_is_admin_admits_only_admins(self):
        self.assertTrue(self._allows(IsAdmin, self.admin))
        self.assertFalse(self._allows(IsAdmin, self.trainer))
        self.assertFalse(self._allows(IsAdmin, self.member))

    def test_is_trainer_admits_only_trainers(self):
        self.assertTrue(self._allows(IsTrainer, self.trainer))
        # An admin is deliberately not a trainer here: "my earnings" belongs to
        # the person who earned it, and an admin has the admin views instead.
        self.assertFalse(self._allows(IsTrainer, self.admin))
        self.assertFalse(self._allows(IsTrainer, self.member))

    def test_is_trainer_or_admin_admits_both_but_not_members(self):
        self.assertTrue(self._allows(IsTrainerOrAdmin, self.trainer))
        self.assertTrue(self._allows(IsTrainerOrAdmin, self.admin))
        self.assertFalse(self._allows(IsTrainerOrAdmin, self.member))

    def test_read_only_lets_anyone_signed_in_read(self):
        for user in (self.member, self.trainer, self.admin):
            self.assertTrue(self._allows(IsAdminOrReadOnly, user, method="get"))

    def test_read_only_lets_only_admins_write(self):
        for method in ("post", "put", "patch", "delete"):
            self.assertTrue(self._allows(IsAdminOrReadOnly, self.admin, method=method))
            self.assertFalse(self._allows(IsAdminOrReadOnly, self.trainer, method=method))
            self.assertFalse(self._allows(IsAdminOrReadOnly, self.member, method=method))

    def test_head_and_options_count_as_reads(self):
        # DRF sends OPTIONS for its browsable API and CORS preflight; treating
        # either as a write would break both for non-admins.
        for method in ("head", "options"):
            self.assertTrue(self._allows(IsAdminOrReadOnly, self.member, method=method))

    def test_anonymous_is_refused_by_every_class(self):
        # The `is_authenticated` guard has to come first: AnonymousUser has no
        # `is_admin`, so a reordered check would raise instead of refusing.
        anon = AnonymousUser()
        for permission in (IsAdmin, IsTrainer, IsTrainerOrAdmin, IsAdminOrReadOnly):
            self.assertFalse(self._allows(permission, anon), permission.__name__)

    def test_a_missing_user_is_refused_rather_than_crashing(self):
        for permission in (IsAdmin, IsTrainer, IsTrainerOrAdmin, IsAdminOrReadOnly):
            self.assertFalse(self._allows(permission, None), permission.__name__)


class IsOwnerOrAdminTests(TenantAPIMixin, APITestCase):
    """Object-level ownership, used by check-ins and workout logs."""

    @classmethod
    def setUpTestData(cls):
        cls.member = make_user("owner_member")
        cls.other = make_user("owner_other")
        cls.trainer = make_user("owner_trainer", role=Role.TRAINER)
        cls.admin = make_user("owner_admin", role=Role.ADMIN)
        cls.row = BodyMeasurement.objects.create(user=cls.member, weight_kg=Decimal("72"))

    def setUp(self):
        self.factory = APIRequestFactory()

    def _allows(self, user, obj, permission=IsOwnerOrAdmin):
        # Same as above: no middleware on a factory request, so the standing
        # the middleware would have resolved is attached by hand.
        from tenancy.resolution import access_for

        request = self.factory.get("/")
        request.user = user
        request.access = access_for(user, self.tenant)
        return bool(permission().has_object_permission(request, APIView(), obj))

    def test_the_owner_may_reach_their_own_row(self):
        self.assertTrue(self._allows(self.member, self.row))

    def test_another_member_may_not(self):
        self.assertFalse(self._allows(self.other, self.row))

    def test_an_admin_may_reach_anyones_row(self):
        self.assertTrue(self._allows(self.admin, self.row))

    def test_a_trainer_is_not_an_owner_by_default(self):
        # This class is plain ownership; roster-aware access is `visible_rows`.
        # Conflating the two would quietly widen every view using this class.
        self.assertFalse(self._allows(self.trainer, self.row))

    def test_owner_field_can_be_renamed_by_a_subclass(self):
        class IsRecorderOrAdmin(IsOwnerOrAdmin):
            owner_field = "recorded_by"

        self.row.recorded_by = self.trainer
        self.row.save(update_fields=["recorded_by"])
        self.assertTrue(self._allows(self.trainer, self.row, permission=IsRecorderOrAdmin))
        self.assertFalse(self._allows(self.other, self.row, permission=IsRecorderOrAdmin))

    def test_a_row_with_no_owner_belongs_to_nobody(self):
        class IsNobodysOrAdmin(IsOwnerOrAdmin):
            owner_field = "missing_field"

        self.assertFalse(self._allows(self.member, self.row, permission=IsNobodysOrAdmin))
        # An admin still gets through -- they short-circuit before the lookup.
        self.assertTrue(self._allows(self.admin, self.row, permission=IsNobodysOrAdmin))

    def test_it_is_a_permission_class(self):
        self.assertTrue(issubclass(IsOwnerOrAdmin, BasePermission))


class VisibleRowsTests(TenantAPIMixin, APITestCase):
    """The Q() that scopes every per-member table."""

    @classmethod
    def setUpTestData(cls):
        cls.trainer = make_user("scope_trainer", role=Role.TRAINER)
        cls.other_trainer = make_user("scope_other_trainer", role=Role.TRAINER)
        cls.admin = make_user("scope_admin", role=Role.ADMIN)
        cls.mine = make_user("scope_mine", trainer=cls.trainer)
        cls.theirs = make_user("scope_theirs", trainer=cls.other_trainer)
        cls.unassigned = make_user("scope_unassigned")

        for member in (cls.mine, cls.theirs, cls.unassigned):
            BodyMeasurement.objects.create(user=member, weight_kg=Decimal("70"))

    def _as(self, user):
        """What `user` is at this gym -- `visible_rows` takes standing, not
        identity, because "is this person an admin" has no answer without
        naming a gym."""
        from tenancy.resolution import access_for

        return access_for(user, self.tenant)

    def _visible_to(self, user):
        rows = BodyMeasurement.objects.filter(visible_rows(self._as(user)))
        return {row.user_id for row in rows}

    def test_a_member_sees_only_their_own(self):
        self.assertEqual(self._visible_to(self.mine), {self.mine.id})

    def test_a_trainer_sees_their_roster(self):
        self.assertEqual(self._visible_to(self.trainer), {self.mine.id})

    def test_a_trainer_does_not_see_another_trainers_roster(self):
        self.assertNotIn(self.theirs.id, self._visible_to(self.trainer))

    def test_a_trainer_does_not_see_unassigned_members(self):
        self.assertNotIn(self.unassigned.id, self._visible_to(self.trainer))

    def test_an_admin_sees_everyone(self):
        self.assertEqual(
            self._visible_to(self.admin),
            {self.mine.id, self.theirs.id, self.unassigned.id},
        )

    def test_an_admin_gets_an_unfiltered_q(self):
        # An empty Q() rather than a filtered one, so callers can add their own
        # filters without an admin silently losing rows to an AND.
        self.assertEqual(len(visible_rows(self._as(self.admin))), 0)

    def test_the_owning_field_can_be_renamed(self):
        # Tables that name the member something other than `user` still scope.
        rows = BodyMeasurement.objects.filter(
            visible_rows(self._as(self.trainer), field="user")
        )
        self.assertEqual({row.user_id for row in rows}, {self.mine.id})


class MayWriteForTests(TenantAPIMixin, APITestCase):
    def _as(self, user):
        from tenancy.resolution import access_for

        return access_for(user, self.tenant)

    @classmethod
    def setUpTestData(cls):
        cls.trainer = make_user("write_trainer", role=Role.TRAINER)
        cls.other_trainer = make_user("write_other_trainer", role=Role.TRAINER)
        cls.admin = make_user("write_admin", role=Role.ADMIN)
        cls.mine = make_user("write_mine", trainer=cls.trainer)
        cls.theirs = make_user("write_theirs", trainer=cls.other_trainer)

    def test_a_member_may_write_for_themselves(self):
        self.assertTrue(may_write_for(self._as(self.mine), self.mine))

    def test_a_member_may_not_write_for_anyone_else(self):
        self.assertFalse(may_write_for(self._as(self.mine), self.theirs))

    def test_an_admin_may_write_for_anyone(self):
        self.assertTrue(may_write_for(self._as(self.admin), self.mine))
        self.assertTrue(may_write_for(self._as(self.admin), self.theirs))

    def test_a_trainer_may_write_for_their_own_member(self):
        self.assertTrue(may_write_for(self._as(self.trainer), self.mine))

    def test_a_trainer_may_not_write_for_someone_elses_member(self):
        self.assertFalse(may_write_for(self._as(self.trainer), self.theirs))

    def test_a_member_without_a_profile_is_refused_not_a_500(self):
        # Trainers and admins have no MemberProfile, and neither does a member
        # created by a path that skipped one. Reaching through `.profile`
        # blindly used to turn "not one of yours" into a server error.
        profileless = User.objects.create_user(
            username="write_profileless", email="p@example.com", password="pass12345"
        )
        self.assertFalse(hasattr(profileless, "profile"))
        self.assertFalse(may_write_for(self._as(self.trainer), profileless))

    def test_a_trainer_may_write_for_themselves(self):
        # Falls out of the first branch, before the roster lookup.
        self.assertTrue(may_write_for(self._as(self.trainer), self.trainer))


class HealthCheckTests(TenantAPIMixin, APITestCase):
    def test_it_answers_without_a_token(self):
        # The frontend calls this before anyone has signed in, to wait out a
        # free-tier cold start; requiring auth would defeat the point.
        resp = self.client.get("/api/health/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "ok")
