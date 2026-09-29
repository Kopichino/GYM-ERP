"""Running the same job once per gym.

Cron and management commands start with no tenant in scope, deliberately: a
tenant-scoped manager refuses to answer rather than quietly reaching across
gyms, so scheduled work has to say which gym it means. That is what this does --
one gym at a time, each inside its own scope.

The alternative, reaching for `.unscoped` to make a command run, would hand the
job every gym's rows at once and lose the isolation the scoped managers exist
to provide. Sweeping is the pattern the nightly reminder already used; this is
that pattern, in one place, for every scheduled job.

One gym's failure does not stop the rest: a branch with a bad address or a
missing plan should not mean nobody else on the platform is swept. Failures are
returned to the caller as well as logged, so a command can report them and exit
non-zero rather than looking like it worked.
"""

import logging

from . import context

logger = logging.getLogger(__name__)


def active_tenants():
    """Every gym a sweep should visit, oldest first so runs are comparable."""
    from .models import Tenant

    return Tenant.objects.filter(is_active=True).order_by("id")


def for_each_tenant(job, tenants=None):
    """Run `job(tenant)` inside each gym's scope.

    Returns `(results, failures)`: `results` is a list of `(tenant, value)` for
    the gyms that ran, `failures` a list of `(tenant, exception)` for those that
    raised. The scope is entered and left around every call, so a gym that
    raises leaves nothing behind for the next one.
    """
    results, failures = [], []
    for tenant in tenants if tenants is not None else active_tenants().iterator():
        try:
            with context.scope(tenant):
                results.append((tenant, job(tenant)))
        except Exception as error:  # noqa: BLE001 -- one gym must not stop the sweep
            logger.exception("sweep failed for tenant %s", tenant.slug)
            failures.append((tenant, error))
    return results, failures
