from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "core"

    def ready(self):
        # Registers the deploy-time checks in core/checks.py. Imported here
        # rather than at module scope so the checks are attached exactly once,
        # after the app registry is populated.
        from . import checks  # noqa: F401
