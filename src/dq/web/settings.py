"""Django settings for the dq web app. Everything deploy-specific comes from the environment."""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from ..cli import PROJECT_ROOT, default_home

WEB_DIR = Path(__file__).resolve().parent

DEBUG = os.environ.get("DQ_DEBUG", "") == "1"


def _secret_key() -> str:
    key = os.environ.get("DJANGO_SECRET_KEY", "")
    if key.startswith("op://"):
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY is an unresolved 1Password reference; run under `op run --env-file=.env`"
        )
    if key:
        return key
    if DEBUG:
        return "dev-only-insecure-key"
    raise ImproperlyConfigured(
        "Set DJANGO_SECRET_KEY (or DQ_DEBUG=1 for local development)"
    )


SECRET_KEY = _secret_key()
ALLOWED_HOSTS = os.environ.get("DQ_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
CSRF_TRUSTED_ORIGINS = [
    f"https://{h}" for h in ALLOWED_HOSTS if "." in h and h != "127.0.0.1"
]

DQ_HOME = Path(os.environ.get("DQ_HOME", str(default_home()))).expanduser()
DQ_HOME.mkdir(parents=True, exist_ok=True)
DQ_CURRICULUM = Path(os.environ.get("DQ_CURRICULUM", str(PROJECT_ROOT / "curriculum")))
DQ_BACKEND = os.environ.get("DQ_BACKEND", "lmstudio")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.auth.middleware.LoginRequiredMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "dq.web.middleware.DqMiddleware",
]

ROOT_URLCONF = "dq.web.urls"
WSGI_APPLICATION = "dq.web.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.jinja2.Jinja2",
        "DIRS": [WEB_DIR / "templates"],
        "OPTIONS": {"environment": "dq.web.jinja.environment"},
    },
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    },
]

# Accounts and sessions live in their own database; the learning data stays in dq.db.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DQ_HOME / "web.sqlite3",
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

LOGIN_URL = "/login"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login"

# Stay logged in on a device for 30 days after its last visit.
SESSION_COOKIE_AGE = 30 * 24 * 3600
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

STATIC_URL = "/static/"
STATICFILES_DIRS = [WEB_DIR / "static"]
WHITENOISE_USE_FINDERS = True

DATA_UPLOAD_MAX_MEMORY_SIZE = 25 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 25 * 1024 * 1024

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.environ.get("DQ_TIME_ZONE", "America/Chicago")
USE_TZ = True
