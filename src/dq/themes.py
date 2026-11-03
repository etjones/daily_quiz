"""Interests: themed word-problem templates ("Pikachu caught {a} berries…").

A theme is a set of story templates, one family per operation. The arithmetic never comes
from a template: a math generator picks the numbers and the answer as usual, and a template
only re-tells that problem as a story about something the child likes. So a themed problem
is graded exactly like the plain one.

Built-in interests live in curriculum/interests/*.toml. A grown-up can add a new interest by
name; a model writes its templates once, and every template passes `validate_template`
before it is stored. Templates end up inside Typst markup on the quiz, so the character set
is an allowlist with no markup characters at all.
"""

import json
import random
import re
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path

from .generators import Problem

MAX_INTERESTS = 4
NAME_MAX = 32
TEMPLATE_MAX = 150
MIN_PER_KIND = 2

# placeholder names per kind; the answer is computed from them by the generator
KINDS: dict[str, tuple[str, ...]] = {
    "add": ("a", "b"),  # a and b more: a + b
    "sub": ("a", "b"),  # a, b go away: a - b
    "compare": ("a", "b"),  # a and b: how many more is a? a - b
    "mul": ("a", "b"),  # a groups of b: a × b
    "div": ("total", "a"),  # total shared into a equal groups: total ÷ a
    "div_rem": ("total", "a"),  # total into a equal groups, with some left over
    "frac_of": ("total", "frac"),  # frac ("one third") of total
    "frac_add": ("a", "b"),  # fraction amounts ("2 3/4"): a + b
    "frac_sub": ("a", "b"),  # fraction amounts: a - b
    "dec_add": ("a", "b"),  # decimal amounts: a + b
    "dec_sub": ("a", "b"),  # decimal amounts: a - b
    "dec_mul": ("a", "b"),  # a (whole) groups of b (decimal amount)
    "dec_div": ("total", "a"),  # total (decimal amount) shared into a (whole) groups
    "area": ("l", "w"),  # rectangle l by w: l × w
    "perimeter": ("l", "w"),  # rectangle l by w: 2 × (l + w)
    "volume": ("l", "w", "h"),  # box l by w by h: l × w × h
}
# Kinds whose blanks are decimal amounts (3.25), so the story needs a unit that can be split.
DECIMAL_KINDS = ("dec_add", "dec_sub", "dec_mul", "dec_div")
KIND_TITLES = {
    "add": "Adding",
    "sub": "Taking away",
    "compare": "Comparing",
    "mul": "Equal groups",
    "div": "Sharing",
    "div_rem": "Sharing with leftovers",
    "frac_of": "A fraction of a group",
    "frac_add": "Adding fractions",
    "frac_sub": "Taking away fractions",
    "dec_add": "Adding decimals",
    "dec_sub": "Taking away decimals",
    "dec_mul": "Groups of a decimal",
    "dec_div": "Sharing a decimal",
    "area": "Area",
    "perimeter": "Perimeter",
    "volume": "Volume",
}
KIND_HELP = {
    "add": "{a} of something, then {b} more join them; asks how many in all",
    "sub": "{a} of something, then {b} of them leave or are used up; asks how many are left",
    "compare": "one has {a}, another has {b} (fewer); asks how many more the first has",
    "mul": "{a} equal groups with {b} in each; asks how many in all",
    "div": "{total} things shared equally into {a} groups; asks how many in each group",
    "div_rem": "{total} things shared equally into {a} groups, with some left over; asks "
    "how many in each group and how many are left over",
    "frac_add": "an amount of {a} and then {b} more, both fractions or mixed numbers like "
    "2 3/4, with a unit that can be split (cups, pizzas, miles, hours); asks how much in all",
    "frac_sub": "an amount of {a}, a fraction or mixed number with a unit that can be "
    "split, and {b} of it is used or eaten; asks how much is left",
    "frac_of": "{total} things, and {frac} of them (a fraction in words, like 'one third') "
    "are picked out; asks how many that is",
    "dec_add": "an amount of {a} and then {b} more, both decimals like 3.25, with a unit "
    "that can be split (kilograms, meters, liters, miles, hours); asks how much in all",
    "dec_sub": "an amount of {a}, a decimal with a unit that can be split, and {b} of it is "
    "used or taken away; asks how much is left",
    "dec_mul": "{a} equal groups (a whole number), each holding {b} of something measured "
    "(a decimal with a unit); asks how much in all",
    "dec_div": "{total} of something measured (a decimal with a unit) shared equally into "
    "{a} groups (a whole number); asks how much in each",
    "area": "a rectangle {l} long and {w} wide, with one length unit used for both (feet, "
    "meters, inches); asks for the area in square units",
    "perimeter": "a rectangle {l} long and {w} wide, with one length unit; asks for the "
    "distance all the way around",
    "volume": "a box {l} long, {w} wide and {h} tall, with one length unit; asks for the "
    "volume in cubic units",
}
# Example numbers, for showing a theme's stories to a grown-up.
SAMPLES: dict[str, dict[str, int | str]] = {
    "add": {"a": 12, "b": 5},
    "sub": {"a": 12, "b": 5},
    "compare": {"a": 12, "b": 5},
    "mul": {"a": 4, "b": 6},
    "div": {"total": 24, "a": 4},
    "div_rem": {"total": 26, "a": 4},
    "frac_of": {"total": 24, "frac": "one third"},
    "frac_add": {"a": "1 3/4", "b": "2/4"},
    "frac_sub": {"a": "1 3/4", "b": "2/4"},
    "dec_add": {"a": "3.25", "b": "1.5"},
    "dec_sub": {"a": "3.25", "b": "1.5"},
    "dec_mul": {"a": 4, "b": "2.5"},
    "dec_div": {"total": "7.5", "a": 3},
    "area": {"l": 8, "w": 5},
    "perimeter": {"l": 8, "w": 5},
    "volume": {"l": 4, "w": 3, "h": 2},
}

# How often a problem that can be themed is themed: stories always could be, bare facts
# (7 × 8) only sometimes, so the practice of plain facts stays.
SHARE = {"story": 0.75, "fact": 0.25}

_LETTER = r"[^\W\d_]"  # any letter, accented ones too; no digits or underscore
_TEXT_RX = re.compile(rf"(?:{_LETTER}|[ .,?!'’:;()&{{}}-])+")
_PLACEHOLDER_RX = re.compile(r"\{([^{}]*)\}")
NAME_RX = re.compile(rf"{_LETTER}(?:{_LETTER}|[ '&-])*")


class ThemeError(ValueError):
    pass


@dataclass
class Template:
    kind: str
    text: str

    def fill(self, nums: dict[str, int | str]) -> str:
        """Whole numbers get thousands commas; decimals and fraction words go in as given."""
        return self.text.format(
            **{k: f"{v:,}" if isinstance(v, int) else v for k, v in nums.items()}
        )


@dataclass
class Theme:
    slug: str
    name: str
    blurb: str = ""
    templates: list[Template] = field(default_factory=list)
    source: str = "built-in"  # built-in | generated

    def of_kind(self, kind: str) -> list[Template]:
        return [t for t in self.templates if t.kind == kind]


def clean_name(raw: str) -> str:
    """A grown-up's interest name, checked: letters, spaces, ' & and -, at most 32 characters.
    Anything else is refused rather than cleaned, since the name goes to a model."""
    name = re.sub(r"\s+", " ", raw).strip()
    if not name:
        raise ThemeError("Give the interest a name.")
    if len(name) > NAME_MAX:
        raise ThemeError(f"Keep the name to {NAME_MAX} characters or fewer.")
    if not NAME_RX.fullmatch(name):
        raise ThemeError("Use only letters, spaces, apostrophes, & and - in the name.")
    return name


def plain_text(s: str) -> bool:
    """Only allowlisted characters (no markup, no digits, no blanks)."""
    return bool(_TEXT_RX.fullmatch(s)) and "{" not in s and "}" not in s


def slugify(name: str) -> str:
    return re.sub(r"[^a-z]+", "-", name.lower()).strip("-")


def validate_template(kind: str, text: str) -> list[str]:
    """Problems with one template; empty means usable."""
    if kind not in KINDS:
        return [f"unknown kind {kind!r}"]
    errs = []
    if len(text) > TEMPLATE_MAX:
        errs.append(f"longer than {TEMPLATE_MAX} characters")
    if not _TEXT_RX.fullmatch(text):
        bad = sorted(set(_TEXT_RX.sub("", text)))
        errs.append(f"characters not allowed: {''.join(bad)!r}")
    found = _PLACEHOLDER_RX.findall(text)
    want = set(KINDS[kind])
    if set(found) != want:
        errs.append(
            f"needs exactly the blanks {sorted(want)}, has {sorted(set(found))}"
        )
    if any(found.count(p) != 1 for p in want):
        errs.append("each blank must appear once")
    if not text.rstrip().endswith("?"):
        errs.append("must end with a question")
    return errs


def validate_theme(theme: Theme) -> list[str]:
    errs = [
        f"{theme.slug}: {t.kind}: {e}: {t.text!r}"
        for t in theme.templates
        for e in validate_template(t.kind, t.text)
    ]
    for kind in KINDS:
        if len(theme.of_kind(kind)) < MIN_PER_KIND:
            errs.append(f"{theme.slug}: fewer than {MIN_PER_KIND} {kind} templates")
    if len({t.text for t in theme.templates}) != len(theme.templates):
        errs.append(f"{theme.slug}: duplicate templates")
    return errs


def from_dict(slug: str, data: dict, source: str) -> Theme:
    return Theme(
        slug=slug,
        name=data["name"],
        blurb=data.get("blurb", ""),
        templates=[
            Template(kind, text)
            for kind in KINDS
            for text in data.get("templates", {}).get(kind, [])
        ],
        source=source,
    )


def to_dict(theme: Theme) -> dict:
    return {
        "name": theme.name,
        "blurb": theme.blurb,
        "templates": {k: [t.text for t in theme.of_kind(k)] for k in KINDS},
    }


def load_builtin(directory: Path) -> dict[str, Theme]:
    out = {}
    for path in sorted(directory.glob("*.toml")) if directory.is_dir() else []:
        with open(path, "rb") as f:
            out[path.stem] = from_dict(path.stem, tomllib.load(f), "built-in")
    return out


def available(builtin: dict[str, Theme], added: list) -> dict[str, Theme]:
    """Every interest a student can pick: the built-in ones, then the ones grown-ups added
    (rows of the `interest` table), sorted by name."""
    out = dict(builtin)
    for row in added:
        out[row["slug"]] = from_dict(row["slug"], json.loads(row["data"]), "generated")
    return dict(sorted(out.items(), key=lambda kv: kv[1].name.lower()))


def _story(p: Problem) -> tuple[str, dict[str, int]] | None:
    """(kind, numbers) for a problem a template can re-tell, else None."""
    m = p.meta
    op = m.get("op")
    if op not in KINDS:
        return None
    nums = {k: m[k] for k in KINDS[op]}
    if min((v for v in nums.values() if isinstance(v, int)), default=2) < 2:
        return None  # "1 home runs", "0 berries": skip rather than mangle the grammar
    return op, nums


def apply(problem: Problem, chosen: list[Theme], rng: random.Random) -> Problem:
    """Maybe re-tell `problem` as a story from one of the child's interests. The answer,
    kind and key are unchanged; only the wording moves."""
    story = _story(problem)
    if not chosen or story is None:
        return problem
    if rng.random() >= SHARE["story" if problem.prose else "fact"]:
        return problem
    kind, nums = story
    options = [t for th in chosen for t in th.of_kind(kind)]
    if not options:
        return problem
    text = rng.choice(options).fill(nums)
    return replace(problem, prompt=text, speech=text, lead="$=$", prose=True)
