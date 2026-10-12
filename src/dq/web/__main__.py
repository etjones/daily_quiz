"""Service entry point: `python -m dq.web`. Reads PORT from the environment or the project's .env and
binds 127.0.0.1 only; a reverse proxy (Caddy) terminates TLS in front of it."""

import os

import uvicorn
from dotenv import load_dotenv

from ..cli import PROJECT_ROOT


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(
        "dq.web.app:create_app",
        factory=True,
        host="127.0.0.1",
        port=port,
        proxy_headers=True,
    )


if __name__ == "__main__":
    main()
