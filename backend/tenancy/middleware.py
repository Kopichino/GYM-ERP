"""Putting the tenant in scope for the duration of one request.

Runs early, before anything touches the ORM, and unwinds on the way out so a
worker thread never carries one gym's scope into the next request.

Authentication happens *after* this in DRF -- the JWT is decoded by the view's
authentication classes, not by Django's session middleware -- so `request.user`
is not reliable here. The tenant is therefore resolved eagerly (it comes from
the URL and needs nobody signed in), while `request.access` is resolved lazily
on first touch, by which point DRF has done its work.
"""

from django.utils.functional import SimpleLazyObject

from . import context
from .resolution import Access, access_for, tenant_from_host, tenant_from_path


class TenantMiddleware:
    """Resolve the gym, hold it in scope, and expose who the caller is to it.

    Sets three things on the request:

    * `request.tenant` -- the gym, or None outside one.
    * `request.access` -- lazily, an `Access` saying what the caller is here.
    * the `tenancy.context` scope, which is what the scoped managers read.

    Requests that name no tenant are left in platform scope rather than being
    rejected outright: the login endpoint, the health check and the platform's
    own surface all legitimately have no gym. They get no tenant-scoped data
    either, because the managers refuse to run without one -- so this fails
    closed without having to enumerate which routes are exempt.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tenant = tenant_from_host(request.get_host())
        if tenant is None:
            tenant, rest = tenant_from_path(request.path_info)
            if tenant is not None:
                # Strip the prefix so the URLconf never sees it. Every existing
                # route keeps working unchanged, and swapping to host-based
                # resolution later deletes this branch rather than rewriting
                # anything downstream.
                request.path_info = rest
                request.path = rest

        request.tenant = tenant
        # Lazy: DRF authenticates inside the view, so request.user is still
        # anonymous at this point in the stack.
        request.access = SimpleLazyObject(
            lambda: access_for(getattr(request, "user", None), tenant)
        )

        if tenant is None:
            with context.platform_scope():
                return self.get_response(request)

        with context.scope(tenant):
            return self.get_response(request)
