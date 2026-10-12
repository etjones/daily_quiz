"""Per-request house-style theme selection (the Django side of `hs.py export`)."""

from django.http import HttpRequest

STATIC_URL = "/static/house-style"
THEMES = (
    "swiss",
    "drafting",
    "brutalist",
    "secession",
    "destijl",
    "proun",
    "setback",
    "piranesi",
    "capsule",
    "brion",
    "memphis",
    "plugin",
    "wasmuth",
)
DEFAULT_THEME = "wasmuth"
MODES = ("dark", "light", "auto")


def house_context(request: HttpRequest) -> dict:
    """Query string wins over the cookie the picker writes, which wins over the default.
    `auto` renders dark; the picker's boot script corrects it before first paint."""
    theme = request.GET.get("theme") or request.COOKIES.get("hs_theme")
    pref = request.GET.get("mode") or request.COOKIES.get("hs_mode")
    pref = pref if pref in MODES else "dark"
    return {
        "hs_static": STATIC_URL,
        "hs_theme": theme if theme in THEMES else DEFAULT_THEME,
        "hs_mode": "dark" if pref == "auto" else pref,
        "hs_mode_pref": pref,
        "hs_picker": True,
        "hs_key": "dq",
    }
