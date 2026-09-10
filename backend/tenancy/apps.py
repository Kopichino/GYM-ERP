from django.apps import AppConfig


class TenancyConfig(AppConfig):
    name = "tenancy"

    def ready(self):
        from .stamping import connect

        connect()

        # A gym's own domain is a cross-origin caller of the platform API, so
        # the static CORS list cannot cover it. corsheaders asks this signal
        # before refusing, which is the supported way to answer per request.
        try:
            from corsheaders.signals import check_request_enabled

            from .hosts import cors_allow_verified_domain

            check_request_enabled.connect(cors_allow_verified_domain)
        except ImportError:  # pragma: no cover - corsheaders is a hard dep
            pass
