"""Service entry point: `python -m dq.web`. Applies migrations, then runs gunicorn on 127.0.0.1:$PORT;
a reverse proxy (Caddy) terminates TLS in front of it. Reads the project's .env for plain settings;
secrets come from the environment (`op run --env-file=.env`)."""

import os
import sys

import django
from django.core.management import call_command
from dotenv import load_dotenv

from ..cli import PROJECT_ROOT


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dq.web.settings")
    django.setup()
    call_command("migrate", interactive=False, verbosity=0)
    port = os.environ.get("PORT", "8000")
    args = ["gunicorn", "dq.web.wsgi", "--bind", f"127.0.0.1:{port}", "--workers", "2"]
    args += ["--forwarded-allow-ips", "127.0.0.1", "--access-logfile", "-"]
    os.execv(sys.executable, [sys.executable, "-m", *args])


if __name__ == "__main__":
    main()
