"""Who may do what, at the gym the request is for.

Every class here answers a question that only makes sense with a gym attached.
"Is this user an admin" has no answer on a platform running many gyms -- the
same person may own one, coach at another, and train at a third. So the
question these ask is "is this user an admin *here*", read from `request.access`
which the tenant middleware resolved from live Membership rows.

That shape is what makes cross-tenant access a uniform refusal. A trainer at
Gym A calling Gym B's API arrives with an `Access` holding no roles, so every
class below says no without any view having to remember to check. There is no
per-endpoint tenant test to forget.

`User.is_admin` and friends were deleted rather than deprecated, deliberately.
A compatibility shim would have let un-migrated call sites keep returning a
plausible answer to the wrong question; an AttributeError is found by the
tests.
"""

from rest_framework.exceptions import NotFound
from rest_framework.permissions import SAFE_METHODS, BasePermission

from tenancy.resolution import Access

#: Returned when the middleware never ran -- a management command, or a test
#: calling a view directly. No roles, so everything is refused, which is the
#: right default for an unresolved request.
NO_ACCESS = Access()


def access(request):
    """What the caller is at the gym this request is for."""
    return getattr(request, "access", None) or NO_ACCESS


def signed_in(request):
    user = getattr(request, "user", None)
    return bool(user and user.is_authenticated)


class IsAdmin(BasePermission):
    """Admin portal only, at this gym.

    Trainers and members are rejected outright, and so is an admin of a
    different gym -- they hold no admin role here, so they are a stranger like
    anybody else.
    """

    def has_permission(self, request, view):
        return signed_in(request) and access(request).is_admin


class IsTrainer(BasePermission):
    def has_permission(self, request, view):
        return signed_in(request) and access(request).is_trainer


class IsTrainerOrAdmin(BasePermission):
    def has_permission(self, request, view):
        current = access(request)
        return signed_in(request) and (current.is_trainer or current.is_admin)


class IsTenantMember(BasePermission):
    """Any standing at all at this gym.

    The floor for anything gym-specific: being signed in is not enough, because
    a signed-in stranger is exactly the cross-tenant case.

    A request that names no gym at all gets a 404 rather than a 403. These
    routes only mean anything at a gym, so "which gym?" has no answer -- and a
    403 would still confirm the route is there.
    """

    def has_permission(self, request, view):
        if not signed_in(request):
            return False
        from tenancy import context

        if context.get() is None:
            raise NotFound()
        return access(request).belongs


class IsAdminOrReadOnly(BasePermission):
    """Anyone who belongs here can read; only an admin here can write.

    Used for announcements, schedule and gallery moderation.
    Reading now requires membership rather than merely being signed in --
    otherwise a stranger could read one gym's noticeboard through another
    gym's login.
    """

    def has_permission(self, request, view):
        if not signed_in(request):
            return False
        current = access(request)
        if request.method in SAFE_METHODS:
            return current.belongs
        return current.is_admin


class IsPlatformStaffOrReadOnly(BasePermission):
    """Anyone who belongs here can read; only platform staff can write.

    For the shared catalogues -- exercises and foods -- which carry no tenant
    column, so every gym reads the same rows. "Is this user an admin here" is
    the wrong question for them: a gym admin writing there writes into every
    other gym at once. `is_staff` is the platform-level flag (it also gates
    Django's /admin/), and staff need no standing at the gym in the URL,
    because the rows are not that gym's.
    """

    def has_permission(self, request, view):
        if not signed_in(request):
            return False
        if request.method in SAFE_METHODS:
            return access(request).belongs
        return request.user.is_staff


class IsOwnerOrAdmin(BasePermission):
    """Members can only see or edit rows that are theirs; admins here, anyone's.

    Object-level only. The tenant boundary is already held by the scoped
    managers, so by the time an object reaches this check it is one of this
    gym's -- this decides ownership within the gym, not between gyms.
    """

    owner_field = "user"

    def has_object_permission(self, request, view, obj):
        if access(request).is_admin:
            return True
        owner = getattr(obj, self.owner_field, None)
        return owner == request.user
