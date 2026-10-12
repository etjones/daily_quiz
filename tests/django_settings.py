import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only")

from dq.web.settings import *

SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
DQ_BACKEND = "none"
