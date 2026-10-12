"""Serve the house style from a Starlette or FastAPI app.

Copied into a project by `hs.py export`. Safe to edit; re-exporting overwrites
it, so keep project-specific choices in the HouseStyle() you construct rather
than in this file.

The whole job is two things a static build does not have to do: point the
templates at cached CSS instead of inlining it, and pick the theme per request
so the first byte of HTML is already right.
"""

import dataclasses
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.staticfiles import StaticFiles

#: Written by ui/picker.js when a reader changes the theme, so the next
#: server-rendered response agrees with what they are already looking at.
THEME_COOKIE = "hs_theme"
MODE_COOKIE = "hs_mode"

MODES = ("dark", "light", "auto")


@dataclasses.dataclass(frozen=True)
class HouseStyle:
    """Where the assets live and how a request picks its look."""

    static_url: str
    themes: tuple[str, ...]
    default_theme: str
    default_mode: str = "dark"
    picker: bool = True
    key: str = "hs"

    def __post_init__(self) -> None:
        if self.default_theme not in self.themes:
            raise ValueError(
                f"default_theme {self.default_theme!r} is not in themes {self.themes!r}"
            )
        if self.default_mode not in MODES:
            raise ValueError(f"default_mode must be one of {MODES}")

    def theme_for(self, request: Request) -> str:
        """Query string wins over cookie wins over the app default. An unknown
        id falls back rather than 404s — a stale cookie must not break a page."""
        asked = request.query_params.get("theme") or request.cookies.get(THEME_COOKIE)
        return asked if asked in self.themes else self.default_theme

    def mode_for(self, request: Request) -> str:
        asked = request.query_params.get("mode") or request.cookies.get(MODE_COOKIE)
        return asked if asked in MODES else self.default_mode

    def context(self, request: Request, **extra: object) -> dict:
        """Merge the house variables into a template context.

        Render with `templates.TemplateResponse(request, name, house.context(
        request, ...))` — current Starlette wants the request first. The
        returned dict also carries "request" so the older two-argument call
        still works.

        `auto` cannot be resolved on the server — nothing in the request says
        what the operating system prefers — so it renders dark and ui/boot.js
        corrects it before first paint. That is the one case with a possible
        flash, and only for readers who chose Auto on a light desktop.
        """
        pref = self.mode_for(request)
        context: dict = {
            "request": request,
            "hs_static": self.static_url.rstrip("/"),
            "hs_theme": self.theme_for(request),
            "hs_mode": "dark" if pref == "auto" else pref,
            "hs_mode_pref": pref,
            "hs_picker": self.picker,
            "hs_key": self.key,
        }
        context.update(extra)
        return context


def mount(app: Starlette, house: HouseStyle, directory: str | Path) -> None:
    """Serve the exported CSS and JS at `house.static_url`."""
    app.mount(
        house.static_url,
        StaticFiles(directory=str(directory)),
        name="house-style",
    )
