"""Who counts as somebody at the gym in scope.

`User` is platform-owned: one account can hold standing at several gyms, so a
query that starts from `User.role` answers "is this person a member anywhere",
which is not the question any gym-facing screen is asking. Reading people off
`Membership` instead is what keeps one gym's reports, call lists and reminders
from naming another gym's people.

Tenant, role and `is_active` are matched in a single `filter()` on purpose.
Split across two calls, each condition could be satisfied by a *different*
membership -- so a trainer here who is a member at another gym would match a
"members here" query.

Fails closed: with no tenant in scope `context.require()` raises rather than
returning the platform.
"""


def people_here(role=None, tenant=None):
    """Accounts with live standing at this gym, optionally in one role."""
    from accounts.models import User

    from . import context
    from .models import Membership  # noqa: F401 -- the reverse name below needs the app loaded

    conditions = {
        "memberships__tenant": tenant or context.require(),
        "memberships__is_active": True,
    }
    if role is not None:
        conditions["memberships__role"] = role
    return User.objects.filter(**conditions).distinct()


def members_here(tenant=None):
    from accounts.models import Role

    return people_here(Role.MEMBER, tenant)


def trainers_here(tenant=None):
    from accounts.models import Role

    return people_here(Role.TRAINER, tenant)


def people_here_or_404(pk, role=None):
    """One person at this gym, or 404.

    The 404 is the point: an account at another gym must be indistinguishable
    from one that does not exist, or the id alone confirms who trains where.
    """
    from django.shortcuts import get_object_or_404

    return get_object_or_404(people_here(role), pk=pk)


def holds_standing_elsewhere(user, tenant=None):
    """Whether `user` has live standing at some gym other than this one.

    An account shared with another gym is not this gym's to re-key. Setting its
    password, changing the email it signs in with or clearing its authenticator
    would hand whoever did it the other gym as well -- which, for an admin of
    gym B who also trains at gym A, is a takeover of gym B.
    """
    from . import context
    from .models import Membership

    return (
        Membership.objects.filter(user=user, is_active=True)
        .exclude(tenant=tenant or context.require())
        .exists()
    )
