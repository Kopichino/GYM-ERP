"""Working out which gym a request is for, and what the caller may do there.

Two ways in, one answer:

* **Host** -- `fitzone-central.example.com`, or a gym's own custom domain once
  those land. This is the destination.
* **Path prefix** -- `/api/t/<slug>/...`, the interim while every gym is still
  on one shared hostname.

They deliberately share this module rather than being two code paths. The
authorisation that follows resolution is the part that must not diverge: if the
path-prefix route were even slightly more permissive than the host route, the
interim would be a hole that stayed open long after the domains arrived.

The prefix is *stripped* from `path_info` once read, so the URLconf downstream
never learns about it. That is what keeps every existing route working
unchanged, and what makes the eventual switch to hosts a deletion rather than a
rewrite.

Nothing here decides what a caller may see. It answers "which gym, and what is
this person to that gym"; the permission classes turn that into yes or no.
"""

import re

from django.utils import timezone

from accounts.models import Role

from .models import Membership, Tenant

#: /api/t/<slug>/rest/of/path
PREFIX = re.compile(r"^/api/t/(?P<slug>[-a-zA-Z0-9_]+)(?P<rest>/.*)?$")


class Access:
    """What one caller is, at one gym.

    Roles are a set, not a value. Somebody can be both a trainer and a member
    at the same gym -- a coach who also trains there -- and the PT diary has
    always assumed as much.

    An instance with no roles is the normal representation of "signed in, but a
    stranger here". It is not an error: a trainer at Gym A hitting Gym B gets
    one of these, and every permission class then says no. That is what makes
    cross-tenant access a uniform refusal rather than something each view has
    to remember to check.
    """

    __slots__ = ("user", "tenant", "roles")

    def __init__(self, user=None, tenant=None, roles=frozenset()):
        self.user = user
        self.tenant = tenant
        self.roles = frozenset(roles)

    @property
    def is_admin(self):
        return Role.ADMIN in self.roles

    @property
    def is_trainer(self):
        return Role.TRAINER in self.roles

    @property
    def is_member(self):
        return Role.MEMBER in self.roles

    @property
    def belongs(self):
        """Whether this caller has any standing at this gym at all."""
        return bool(self.roles)

    def __repr__(self):
        return f"<Access {self.user} @ {self.tenant}: {sorted(self.roles) or 'none'}>"


def tenant_from_host(host):
    """The gym a hostname belongs to, or None.

    Only **verified** domains resolve. An unverified row is a claim nobody has
    proved yet, and honouring it would make "add a domain" a way to be served
    another gym's data -- the verification step exists precisely to stand
    between those two things.

    The port is stripped because `request.get_host()` includes it in
    development (`localhost:8000`) and a stored hostname never does.
    """
    if not host:
        return None

    hostname = host.split(":")[0].strip().lower().rstrip(".")
    if not hostname:
        return None

    from .models import Domain

    domain = (
        Domain.unscoped.filter(hostname=hostname, verified_at__isnull=False)
        .select_related("tenant")
        .first()
    )
    if domain is None or not domain.tenant.is_active:
        return None
    return domain.tenant


def tenant_from_path(path):
    """(tenant, remaining path) for a `/api/t/<slug>/` request, else (None, None).

    Returns the tenant even when inactive; whether a suspended gym may be used
    is a policy question for the middleware, not a routing one.
    """
    match = PREFIX.match(path or "")
    if not match:
        return None, None
    tenant = Tenant.objects.filter(slug=match.group("slug")).first()
    if tenant is None:
        return None, None
    # Only the `/t/<slug>` segment comes off: the URLconf still mounts
    # everything under /api/, so putting that back is what lets every existing
    # route keep working untouched.
    return tenant, "/api" + (match.group("rest") or "/")


def access_for(user, tenant, on=None):
    """What `user` is at `tenant`, read fresh from Membership.

    Deliberately a query per request rather than a claim in the token. A role
    baked into a 15-minute JWT keeps asserting itself for 15 minutes after it
    is revoked, and "sacked trainer still has the roster" is not a window worth
    trading a lookup for.
    """
    if user is None or not user.is_authenticated or tenant is None:
        return Access(user=user, tenant=tenant)

    on = on or timezone.localdate()
    rows = Membership.objects.filter(user=user, tenant=tenant, is_active=True)
    roles = {row.role for row in rows if row.is_current(on)}
    return Access(user=user, tenant=tenant, roles=roles)
