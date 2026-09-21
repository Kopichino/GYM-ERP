from django.apps import AppConfig


class InstructorsConfig(AppConfig):
    """Kept only so its migrations stay in the graph.

    Instructor profiles were removed -- a class now names the trainer's own
    account. The app cannot simply be uninstalled: schedule_app's first
    migration and two tenancy backfills name migrations here as dependencies,
    and dropping it would leave `migrate` unable to build its graph on any
    database that has already run them. It holds no models, views or URLs.
    """

    name = "instructors"
