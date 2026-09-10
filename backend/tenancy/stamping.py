"""Filling in the tenant on rows that do not name one.

The scoped managers answer "which rows may I read". This answers the other
half: a row written inside a tenant's request belongs to that tenant, and
nobody should have to remember to say so. Without it, `Expense.objects.create(...)`
inside a scope writes a row with a null tenant which the same manager then
refuses to read back -- created successfully and invisible, which is the most
confusing failure available.

A `pre_save` receiver rather than an overridden `create()`, because rows are
also written as `Model(...)` followed by `.save()`, through serializers, and by
`update_or_create`. All of those funnel through `pre_save`; only `create` funnels
through the manager.

An explicit tenant always wins. Cross-tenant writes are a real operation for
platform tooling, and this must not silently overwrite one.
"""

from django.db.models.signals import pre_save

from . import context


def stamp(sender, instance, **kwargs):
    field = getattr(sender, "tenant_field", None)
    if field is None:
        return
    # Already assigned -- by the caller, by a fixture, or by the backfill.
    if getattr(instance, f"{field}_id", None) is not None:
        return

    tenant = context.get()
    if tenant is None:
        # Platform scope, a management command, or a migration. Leaving it null
        # is right: the manager will refuse to read it back, which is a loud
        # failure rather than a row quietly filed under the wrong gym.
        return

    if field == "organisation":
        instance.organisation_id = tenant.organisation_id
    else:
        instance.tenant_id = tenant.pk


def connect():
    # One global receiver that filters on `tenant_field`, rather than a
    # connection per model: a model added later is covered by declaring the
    # attribute, with nothing to remember to wire up.
    pre_save.connect(stamp, dispatch_uid="tenancy.stamp_tenant")
