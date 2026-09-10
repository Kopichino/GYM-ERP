"""The tenant the current request is acting on.

Held in a `ContextVar` rather than passed down through every call, because the
alternative is threading a `tenant` argument through ~400 ORM call sites and
several hundred service functions -- and the one place somebody forgets is a
cross-tenant leak rather than a TypeError.

The rule that makes this safe is that it **fails closed**. `require()` raises
when no tenant is set, so a query that should have been scoped and wasn't
produces a loud error rather than quietly returning every gym's rows. Code that
genuinely runs outside any tenant -- the platform's own admin, a management
command sweeping every gym -- says so explicitly with `platform_scope()`.

ContextVar rather than threading.local: it is correct under async and under
threads, and each request gets its own value without any cleanup discipline.
"""

from contextlib import contextmanager
from contextvars import ContextVar

#: The tenant in force. Unset means "nobody has said yet", which is an error to
#: read; `PLATFORM` means "deliberately no tenant", which is allowed.
_current = ContextVar("current_tenant", default=None)

#: Sentinel for work that is legitimately not about one gym.
PLATFORM = object()


class TenantScopeError(RuntimeError):
    """A tenant-scoped query ran with no tenant in scope.

    Deliberately not caught anywhere: it means a request reached data access
    without going through tenant resolution, which is a bug that must be fixed
    rather than handled.
    """


def get():
    """The current tenant, or None outside any scope. Prefer `require()`."""
    value = _current.get()
    return None if value is PLATFORM else value


def is_platform():
    return _current.get() is PLATFORM


def require():
    """The current tenant, or raise. This is what scoped managers call."""
    value = _current.get()
    if value is None:
        raise TenantScopeError(
            "No tenant in scope. A request must resolve a tenant before touching "
            "tenant-scoped data; work that is genuinely platform-wide has to say "
            "so with tenancy.context.platform_scope()."
        )
    if value is PLATFORM:
        raise TenantScopeError(
            "Running in platform scope, which has no single tenant. Filter "
            "explicitly by tenant, or use the model's .unscoped manager."
        )
    return value


def set(tenant):  # noqa: A001 -- reads as tenancy.context.set(...)
    """Set the tenant and return the token needed to restore the previous one."""
    return _current.set(tenant)


def reset(token):
    _current.reset(token)


@contextmanager
def scope(tenant):
    """Run a block with `tenant` in force."""
    token = _current.set(tenant)
    try:
        yield tenant
    finally:
        _current.reset(token)


@contextmanager
def platform_scope():
    """Run a block that is deliberately not about one gym.

    Used by the platform admin, by cross-tenant management commands, and by the
    migration backfill. Scoped querysets still refuse to run inside it -- the
    point is to distinguish "no tenant because nobody set one" from "no tenant
    because this genuinely spans all of them", so the second has to reach for
    `.unscoped` and say what it is doing.
    """
    token = _current.set(PLATFORM)
    try:
        yield
    finally:
        _current.reset(token)
