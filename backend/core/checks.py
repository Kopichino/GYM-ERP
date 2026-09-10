"""Deploy-time checks for things that are quietly weaker than they look.

A system check rather than a comment, because the failure mode here is a
configuration that looks correct and behaves correctly right up until load or a
restart. `manage.py check --deploy` runs in CI, so this surfaces on every
build rather than at the moment someone needs the limit to have worked.
"""

from django.conf import settings
from django.core.checks import Warning, register


@register("security", deploy=True)
def throttle_state_survives_a_restart(app_configs, **kwargs):
    """Warn when rate limiting is held in per-process memory in production.

    DRF keeps every throttle counter in the default cache. On LocMemCache that
    is per-worker and is discarded on restart -- and on Render's free tier the
    service sleeps after fifteen minutes idle, so the counters are discarded
    routinely rather than rarely. The login limit and the per-username guessing
    limit both depend on this, and both silently stop being limits.
    """
    if settings.DEBUG:
        return []

    backend = settings.CACHES.get("default", {}).get("BACKEND", "")
    if "locmem" not in backend.lower():
        return []

    return [
        Warning(
            "Rate-limit state is stored in per-process memory.",
            hint=(
                "DRF throttling counts requests in the default cache. With "
                "LocMemCache each worker keeps its own count and every restart "
                "resets it, so the login and per-username limits do not hold. "
                "Set REDIS_URL to a shared cache."
            ),
            id="security.W901",
        )
    ]
