"""
Django settings for the gymerp project.

Environment-driven so the exact same codebase runs locally (SQLite, DEBUG=True)
and in production (Postgres on Neon, DEBUG=False) without code changes -- only
the .env / host environment variables differ. See backend/.env.example.
"""

from pathlib import Path

import environ
from corsheaders.defaults import default_headers as cors_default_headers

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
)
# Local dev reads backend/.env; in production these come from the host's
# real environment variables instead, so a missing .env file is fine there.
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="django-insecure-dev-only-change-me")
DEBUG = env.bool("DEBUG", default=False)
# A list subclass, so a gym that verifies its own domain is served without a
# redeploy. The configured entries below are the platform's own hosts and keep
# behaving exactly as before; see tenancy/hosts.py.
from tenancy.hosts import DynamicAllowedHosts  # noqa: E402

ALLOWED_HOSTS = DynamicAllowedHosts(
    env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
)

# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # third-party
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "cloudinary_storage",
    "cloudinary",
    # local apps
    "core",
    # Multi-tenancy: must precede the apps whose models carry its FKs.
    "tenancy",
    "accounts",
    "attendance",
    "workouts",
    "announcements",
    "instructors",
    "schedule_app",
    "gallery",
    "billing",
    "dataimport",
    "bodystats",
    "devices",
    "crm",
    "expenses",
    "invoicing",
    "commissions",
    "reports",
    "nutrition",
    "referrals",
    "notifications",
    "messaging",
    "branding",
    "gamification",
    "shifts",
    "pt",
    "feedback",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # After authentication so request.user exists for session-authenticated
    # views, and before anything that touches the ORM. DRF authenticates later
    # still, inside the view, which is why request.access is lazy.
    "tenancy.middleware.TenantMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "gymerp.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "gymerp.wsgi.application"

# Database
# Local dev: no DATABASE_URL set -> falls back to SQLite automatically.
# Production: DATABASE_URL points at the free Neon Postgres instance.
DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
    )
}

AUTH_USER_MODEL = "accounts.User"

# --- Cache (throttle state lives here) ---------------------------------
#
# Not an optimisation. DRF keeps every throttle counter in this cache, so
# without a shared one the login rate limit and the per-username guessing limit
# are per-process and are wiped whenever the process restarts. On Render's free
# tier the service sleeps after fifteen minutes idle, which means an attacker
# gets a fresh budget after any quiet spell and the limits are close to
# decorative.
#
# LocMemCache stays the default so a developer needs nothing installed. Set
# REDIS_URL in production and the limits start actually holding; `core.checks`
# warns at deploy time when it is missing, so the weak state is loud rather
# than assumed.
REDIS_URL = env("REDIS_URL", default="")

if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            # Named, so separate processes are visibly separate rather than
            # appearing to share an anonymous default.
            "LOCATION": "ironcore-local",
        }
    }


# --- Django admin exposure ---------------------------------------------
#
# The admin is a full read/write console over every table, guarded by a
# password alone -- no JWT, no tenant scoping, no 2FA. Left at the default
# path it is the single most valuable thing an attacker can find, and it is
# found by scanning for "/admin/" and nothing cleverer than that.
#
# Two dials, both off by default so nothing changes for an existing install:
#   DJANGO_ADMIN_ENABLED=False  drops the route entirely (the right answer for
#                               production once day-to-day work happens in the
#                               app's own admin dashboard);
#   DJANGO_ADMIN_URL=<segment>  moves it somewhere unguessable, which is not
#                               security on its own but removes it from the
#                               undirected scanning that finds it today.
DJANGO_ADMIN_ENABLED = env.bool("DJANGO_ADMIN_ENABLED", default=True)
DJANGO_ADMIN_URL = env("DJANGO_ADMIN_URL", default="admin/").lstrip("/")



AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        # Django's default is 8. This product holds payment history, health
        # measurements and biometric enrolment ids, and its admin accounts can
        # read an entire gym's book -- 8 is short for that, and length is the
        # one password rule that reliably helps.
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = env("TIME_ZONE", default="UTC")
USE_I18N = True
USE_TZ = True

# Static files (served by WhiteNoise directly from the Django process --
# no separate static host needed on the Render free tier)
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Media (user-uploaded photos/videos) -- Cloudinary in production, because
# Render's free-tier filesystem is ephemeral and wiped on redeploy. Falls
# back to local disk when no Cloudinary credentials are configured (local
# dev only) so the gallery/instructor-photo/profile-photo features are
# testable without a Cloudinary account.
CLOUDINARY_CLOUD_NAME = env("CLOUDINARY_CLOUD_NAME", default="")
if CLOUDINARY_CLOUD_NAME:
    default_storage_backend = "cloudinary_storage.storage.MediaCloudinaryStorage"
    CLOUDINARY_STORAGE = {
        "CLOUD_NAME": CLOUDINARY_CLOUD_NAME,
        "API_KEY": env("CLOUDINARY_API_KEY", default=""),
        "API_SECRET": env("CLOUDINARY_API_SECRET", default=""),
    }
else:
    default_storage_backend = "django.core.files.storage.FileSystemStorage"
    MEDIA_URL = "media/"
    MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {"BACKEND": default_storage_backend},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- DRF / JWT auth ---------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/hour",
        "user": "1000/hour",
        "login": "10/min",
        # Per-username, so credential stuffing from rotating IPs is limited by
        # whose account it is aimed at rather than only by where it comes from.
        "login_attempt": "10/min",
        # Forgot-password requests, per IP. Loose enough for a gym's shared
        # Wi-Fi, tight enough that the endpoint is no use as a mail cannon.
        "password_reset": "10/hour",
        "checkinout": "30/min",
        "checkout": "20/min",
        # Per lead key, not per IP -- a gym's form sits behind their CDN so
        # visitors share an address, and IP limiting would let one gym's spam
        # spend every other gym's allowance.
        "leads": "30/hour",
    },
}

from datetime import timedelta  # noqa: E402

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# Refresh token is delivered as an httpOnly cookie (set by the login/refresh
# views in accounts.views), not returned in the JSON body, to reduce XSS risk.
JWT_REFRESH_COOKIE_NAME = "refresh_token"
JWT_REFRESH_COOKIE_SECURE = not DEBUG
JWT_REFRESH_COOKIE_SAMESITE = "None" if not DEBUG else "Lax"

# --- CORS / CSRF (frontend is a separate origin: Vercel) ---------------

CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS", default=["http://localhost:5173", "http://127.0.0.1:5173"]
)
CORS_ALLOW_CREDENTIALS = True

# The gym's website sends its lead key in a header, and a header the preflight
# does not list is a header the browser refuses to send -- so the form we hand
# owners would fail before it ever reached a view.
CORS_ALLOW_HEADERS = (*cors_default_headers, "x-lead-key")
CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS", default=["http://localhost:5173", "http://127.0.0.1:5173"]
)

# --- Production security hardening (no-ops locally where DEBUG=True) ---

# Browsers only accept a domain onto the HSTS preload list at a year or more.
# Announcing `preload` under a shorter max-age is not a smaller commitment --
# it is a submission that gets rejected, while still telling every browser that
# already has the header to refuse plain HTTP for the stated window.
HSTS_PRELOAD_MINIMUM_SECONDS = 31_536_000  # one year

# Ramp this deliberately. HSTS is the one header that cannot be walked back
# quickly: a browser that has seen it refuses http:// for the full duration,
# whatever the server later says. A week is a safe starting point; raise it
# once every subdomain is known to be HTTPS-only, and only then does preload
# become available.
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=60 * 60 * 24 * 7)

if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    # Claimed only when the max-age actually qualifies, so the two settings
    # cannot disagree with each other.
    SECURE_HSTS_PRELOAD = SECURE_HSTS_SECONDS >= HSTS_PRELOAD_MINIMUM_SECONDS
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
else:
    # No HSTS locally: a stray header on localhost makes every other project on
    # that hostname unreachable over plain HTTP, and it is not easy to undo.
    SECURE_HSTS_SECONDS = 0

# W021 fires whenever SECURE_HSTS_PRELOAD is False, which is the correct state
# here until SECURE_HSTS_SECONDS reaches a year -- the check cannot tell a
# deliberate "not yet" from an oversight. Silenced rather than satisfied,
# because satisfying it under a short max-age is the mismatch this block
# exists to prevent. core/tests_transport_security.py holds the real invariant.
SILENCED_SYSTEM_CHECKS = ["security.W021"]

# --- Error monitoring (free tier, optional) -----------------------------

# --- Gym identity, printed on GST invoices -----------------------------

GYM_NAME = env("GYM_NAME", default="IRONCORE")
GYM_GSTIN = env("GYM_GSTIN", default="")
# The gym's own state. A sale to the same state splits into CGST + SGST;
# anywhere else is charged as IGST.
GYM_STATE = env("GYM_STATE", default="")
GST_RATE = env("GST_RATE", default="18")

# --- Outgoing email ------------------------------------------------------

# Without SMTP credentials mail is printed to the console rather than swallowed,
# so a developer running the reminder sweep can read exactly what a member would
# have received instead of wondering whether anything happened.
EMAIL_HOST = env("EMAIL_HOST", default="")
if EMAIL_HOST:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_PORT = env.int("EMAIL_PORT", default=587)
    EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
    EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
    EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# --- Outgoing email identity --------------------------------------------
# Mail to gym *owners* -- billing, support, service notices -- always comes
# from here, never dressed as their own gym. A message telling an owner their
# subscription lapsed must not look like it came from themselves.
PLATFORM_FROM_EMAIL = env("PLATFORM_FROM_EMAIL", default="")
# Account-level Postmark token; without it a gym can hold a sending domain but
# no DKIM record can be issued. See tenancy/email_provider.py.
POSTMARK_ACCOUNT_TOKEN = env("POSTMARK_ACCOUNT_TOKEN", default="")
EMAIL_SPF_INCLUDE = env("EMAIL_SPF_INCLUDE", default="spf.mtasv.net")

# --- Custom domains -----------------------------------------------------
# Optional. With both set, verifying a domain also registers it with Render so
# they issue the certificate; without them the domain is verified and the
# operator adds it in the host dashboard by hand. See tenancy/certificates.py.
RENDER_API_KEY = env("RENDER_API_KEY", default="")
RENDER_SERVICE_ID = env("RENDER_SERVICE_ID", default="")

DEFAULT_FROM_EMAIL = env(
    "DEFAULT_FROM_EMAIL", default=f"{GYM_NAME} <no-reply@example.com>"
)

# --- Password reset -----------------------------------------------------
# Where the link in a reset email points: the frontend's own page, which posts
# the new password back to the API. Must be the deployed frontend's address in
# production, or members are emailed a link to localhost.
FRONTEND_URL = env("FRONTEND_URL", default="http://localhost:5173")
# A day rather than Django's three: long enough to find the email, short enough
# that one sitting in an old inbox is not a standing way into the account.
PASSWORD_RESET_TIMEOUT = 60 * 60 * 24

# --- Online payments (Razorpay) -----------------------------------------

# Leave the key blank and online payment is simply off: the member portal asks
# `/api/billing/online/config/` first and hides the button, rather than offering
# a payment that would fail at the gateway.
RAZORPAY_KEY_ID = env("RAZORPAY_KEY_ID", default="")
RAZORPAY_KEY_SECRET = env("RAZORPAY_KEY_SECRET", default="")
# Issued per webhook endpoint in the Razorpay dashboard -- not the API secret.
RAZORPAY_WEBHOOK_SECRET = env("RAZORPAY_WEBHOOK_SECRET", default="")
RAZORPAY_CURRENCY = env("RAZORPAY_CURRENCY", default="INR")

# --- WhatsApp Business (Meta Cloud API) ---------------------------------

# Blank credentials mean WhatsApp is simply off: the admin portal hides the tab
# and the reminder command says so rather than failing halfway through a sweep.
WHATSAPP_TOKEN = env("WHATSAPP_TOKEN", default="")
WHATSAPP_PHONE_NUMBER_ID = env("WHATSAPP_PHONE_NUMBER_ID", default="")
# Chosen by us and typed into Meta's dashboard; echoed back on subscription.
WHATSAPP_VERIFY_TOKEN = env("WHATSAPP_VERIFY_TOKEN", default="")
# Meta's app secret, used to sign every webhook body. Without it, webhooks are
# refused -- an unverifiable message must never reach the assistant.
WHATSAPP_APP_SECRET = env("WHATSAPP_APP_SECRET", default="")

# The assistant falls back to Claude only for questions its own matcher doesn't
# recognise, and only with facts already read from the database. No key means
# no model call and an honest "here's what I can answer".
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY", default="")
ASSISTANT_MODEL = env("ASSISTANT_MODEL", default="claude-sonnet-5")

SENTRY_DSN = env("SENTRY_DSN", default="")
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        traces_sample_rate=0.1,
        send_default_pii=False,
    )
