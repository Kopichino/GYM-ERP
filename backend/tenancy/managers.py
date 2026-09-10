"""Managers that scope a model to the tenant in force.

Installed as the **default** manager on every tenant-owned model, so `.objects`
is already filtered and the ~400 existing ORM call sites become safe without
being rewritten. A forgotten `.filter(tenant=...)` is then a non-event rather
than a leak, which is the only way this stays correct as the codebase grows.

Two escape hatches, both deliberately awkward to type:

* `.unscoped` -- every row, every tenant. For the platform admin, the backfill,
  and cross-tenant reporting. Grep-able in review precisely because it is ugly.
* `tenancy.context.platform_scope()` -- says a whole block is not about one gym.

`Model.objects` raises rather than returning everything when no tenant is set.
Returning everything would be the same bug this class exists to prevent, and a
silent empty queryset would be worse still: the request would look like it
worked and quietly show nothing.
"""

from django.db import models

from . import context


class TenantQuerySet(models.QuerySet):
    def for_tenant(self, tenant):
        return self.filter(**{self.model.tenant_field: tenant})

    def for_organisation(self, organisation):
        field = self.model.tenant_field
        if field == "organisation":
            return self.filter(organisation=organisation)
        return self.filter(**{f"{field}__organisation": organisation})


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):
    """Default manager: every read and write is confined to the current tenant."""

    def get_queryset(self):
        tenant = context.require()
        field = self.model.tenant_field
        if field == "organisation":
            # Organisation-owned config: a branch sees its own brand's rows.
            return super().get_queryset().filter(organisation=tenant.organisation_id)
        return super().get_queryset().filter(**{field: tenant})


class UnscopedManager(models.Manager.from_queryset(TenantQuerySet)):
    """Every row, in every tenant. Only for platform-level work."""


class TenantOwnedModel(models.Model):
    """Base for anything a branch owns.

    Subclasses declare `tenant_field` -- "tenant" for operational rows,
    "organisation" for shared configuration -- and get both managers. `objects`
    is first so it is the default manager Django uses for related descriptors
    and for `Model._base_manager` fallbacks.
    """

    #: Which FK carries ownership. Overridden to "organisation" on shared config.
    tenant_field = "tenant"

    objects = TenantManager()
    unscoped = UnscopedManager()

    class Meta:
        abstract = True
