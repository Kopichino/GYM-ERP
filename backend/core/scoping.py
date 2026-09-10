"""Row-level visibility within one gym.

These take an `Access` -- what the caller is *at the gym this request is for* --
rather than a `User`, because "is this person an admin" has no answer on a
platform running many gyms.

**On the bare `Q()` for admins.** It means "no further filter", which is only
safe because the queryset it is applied to came from a tenant-scoped manager
and is therefore already confined to one gym. Before multi-tenancy this said
"every row"; it now says "every row here". That distinction rests entirely on
the manager, which is why `tenancy.tests_isolation` asserts that every
tenant-owned model actually uses one -- if a model ever slips out of that net,
this line is where it would turn into a leak.
"""

from django.db.models import Q


def visible_rows(access, field="user"):
    """Q() limiting a queryset to the rows `access` is allowed to read.

    Members see only their own; a trainer additionally sees the members
    assigned to them; an admin sees everything in this gym. `field` names the
    FK to the owning member, so this works for any per-member table.
    """
    if access.is_admin:
        return Q()
    if access.is_trainer:
        return Q(**{field: access.user}) | Q(**{f"{field}__profile__trainer": access.user})
    return Q(**{field: access.user})


def may_write_for(access, member):
    """Whether the caller may create or edit rows belonging to `member`."""
    actor = access.user
    if actor == member or access.is_admin:
        return True
    # Not every account has a member profile -- trainers and admins do not, and
    # neither does a member created by a path that skipped one. Reaching
    # through `.profile` blindly turned "not one of your members" into a 500.
    profile = getattr(member, "profile", None)
    return access.is_trainer and getattr(profile, "trainer_id", None) == actor.id
