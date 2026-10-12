"""Problem generators for math skills.

Each generator takes a seeded `random.Random` plus the `params` table from the
curriculum TOML, and returns one `Problem`. Prompts are Typst markup, evaluated by
the templates with these helpers in scope: qbox, fracbar, numline, dots.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Callable

# ---------------------------------------------------------------------------
# data type
# ---------------------------------------------------------------------------


@dataclass
class Problem:
    prompt: str                 # Typst markup shown to the child
    answer: str                 # canonical answer string
    kind: str = "int"           # int | int_rem | frac | symbol | text
    lead: str = "$=$"           # Typst markup printed just before the answer box
    speech: str = ""            # what a parent reads aloud for an oral quiz
    key: str = ""               # identity for de-duplication
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "prompt": self.prompt, "answer": self.answer, "kind": self.kind,
            "lead": self.lead, "speech": self.speech, "key": self.key,
        }


REGISTRY: dict[str, Callable[..., Problem]] = {}


def register(name: str):
    def deco(fn):
        REGISTRY[name] = fn
        return fn
    return deco


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
         "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
         "seventeen", "eighteen", "nineteen"]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def say(n: int) -> str:
    """English words for 0..999 (for parent read-aloud scripts)."""
    if n < 20:
        return _ONES[n]
    if n < 100:
        t, o = divmod(n, 10)
        return _TENS[t] + (f"-{_ONES[o]}" if o else "")
    h, r = divmod(n, 100)
    return f"{_ONES[h]} hundred" + (f" {say(r)}" if r else "")


_FRAC_NAMES = {2: "half", 3: "third", 4: "fourth", 5: "fifth", 6: "sixth", 8: "eighth", 10: "tenth"}


def say_frac(n: int, d: int) -> str:
    name = _FRAC_NAMES.get(d, f"{d}ths")
    if d == 2:
        return "one half" if n == 1 else f"{say(n)} halves"
    return f"{say(n)} {name}" + ("" if n == 1 else "s")


def _pick(rng: random.Random, lohi, multiple_of: int = 1) -> int:
    lo, hi = lohi
    if multiple_of > 1:
        vals = [v for v in range(lo, hi + 1) if v % multiple_of == 0]
        if not vals:
            raise ValueError(f"no multiple of {multiple_of} in {lohi}")
        return rng.choice(vals)
    return rng.randint(lo, hi)


def _has_carry(x: int, y: int) -> bool:
    carry = 0
    while x or y or carry:
        s = x % 10 + y % 10 + carry
        if s >= 10:
            return True
        carry = 0
        x //= 10
        y //= 10
    return False


def _has_borrow(x: int, y: int) -> bool:
    borrow = 0
    while x or y:
        dx, dy = x % 10, y % 10 + borrow
        if dx < dy:
            return True
        borrow = 0
        x //= 10
        y //= 10
    return False


def _frac_tex(n: int, d: int) -> str:
    return f"{n}/{d}"


def _try(rng, fn, attempts: int = 400):
    for _ in range(attempts):
        out = fn()
        if out is not None:
            return out
    raise RuntimeError("generator could not satisfy its constraints; check params")


# ---------------------------------------------------------------------------
# number sense
# ---------------------------------------------------------------------------


@register("skip_count")
def gen_skip_count(rng, steps, start_max=20, length=6) -> Problem:
    step = rng.choice(steps)
    max_k = max(0, start_max // step)
    start = step * rng.randint(0, max_k)
    seq = [start + step * i for i in range(length)]
    hide = rng.randint(1, length - 2)
    shown = [("?" if i == hide else str(v)) for i, v in enumerate(seq)]
    return Problem(
        prompt=", ".join(shown),
        answer=str(seq[hide]), kind="int", lead="$? =$",
        speech="Count by " + say(step) + "s: " + ", ".join(
            ("what comes next" if s == "?" else say(int(s))) for s in shown) + ".",
        key=f"skip:{step}:{start}:{hide}",
    )


@register("place_value")
def gen_place_value(rng, mode="compose", digits=2) -> Problem:
    if digits == 2:
        n = rng.randint(11, 99)
        t, o = divmod(n, 10)
        if rng.random() < 0.5:
            return Problem(
                prompt=f"{t} tens and {o} ones", answer=str(n), kind="int", lead="$=$",
                speech=f"{say(t)} tens and {say(o)} ones. What number is that?", key=f"pv2c:{n}")
        if rng.random() < 0.5:
            return Problem(
                prompt=f"How many tens in ${n}$?", answer=str(t), kind="int", lead="$=$",
                speech=f"How many tens are in {say(n)}?", key=f"pv2t:{n}")
        return Problem(
            prompt=f"How many ones in ${n}$?", answer=str(o), kind="int", lead="$=$",
            speech=f"How many ones are in {say(n)}?", key=f"pv2o:{n}")
    n = rng.randint(101, 999)
    h, rest = divmod(n, 100)
    t, o = divmod(rest, 10)
    r = rng.random()
    if r < 0.5:
        return Problem(
            prompt=f"{h} hundreds, {t} tens, {o} ones", answer=str(n), kind="int", lead="$=$",
            speech=f"{say(h)} hundreds, {say(t)} tens, {say(o)} ones. What number is that?", key=f"pv3c:{n}")
    if r < 0.75:
        return Problem(
            prompt=f"How many hundreds in ${n}$?", answer=str(h), kind="int", lead="$=$",
            speech=f"How many hundreds are in {say(n)}?", key=f"pv3h:{n}")
    return Problem(
        prompt=f"How many tens in the middle of ${n}$? (the tens digit)", answer=str(t), kind="int", lead="$=$",
        speech=f"What is the tens digit of {say(n)}?", key=f"pv3t:{n}")


@register("compare")
def gen_compare(rng, range, allow_equal=False) -> Problem:  # noqa: A002
    lo, hi = range
    a = rng.randint(lo, hi)
    b = rng.randint(lo, hi)
    if not allow_equal:
        while b == a:
            b = rng.randint(lo, hi)
    ans = "<" if a < b else (">" if a > b else "=")
    return Problem(
        prompt=f"#box[${a}$] #h(2.2em) #box[${b}$]",
        answer=ans, kind="symbol", lead="Write < or >",
        speech=f"Which is bigger, {say(a)} or {say(b)}? Say less than or greater than.",
        key=f"cmp:{a}:{b}")


# ---------------------------------------------------------------------------
# add / subtract
# ---------------------------------------------------------------------------


@register("add")
def gen_add(rng, a, b, max_sum=None, min_sum=0, equal=False, regroup="any", multiple_of=1) -> Problem:
    def attempt():
        x = _pick(rng, a, multiple_of)
        y = x if equal else _pick(rng, b, multiple_of)
        s = x + y
        if max_sum is not None and s > max_sum:
            return None
        if s < min_sum:
            return None
        if regroup == "none" and _has_carry(x, y):
            return None
        if regroup == "yes" and not _has_carry(x, y):
            return None
        return x, y

    x, y = _try(rng, attempt)
    return Problem(prompt=f"${x} + {y}$", answer=str(x + y), kind="int", lead="$=$",
                   speech=f"{say(x)} plus {say(y)}", key=f"add:{x}:{y}")


@register("sub")
def gen_sub(rng, a, b, regroup="any", multiple_of=1) -> Problem:
    def attempt():
        x = _pick(rng, a, multiple_of)
        y = _pick(rng, b, multiple_of)
        if y > x:
            return None
        if regroup == "none" and _has_borrow(x, y):
            return None
        if regroup == "yes" and not _has_borrow(x, y):
            return None
        return x, y

    x, y = _try(rng, attempt)
    return Problem(prompt=f"${x} - {y}$", answer=str(x - y), kind="int", lead="$=$",
                   speech=f"{say(x)} minus {say(y)}", key=f"sub:{x}:{y}")


@register("missing_addend")
def gen_missing_addend(rng, total, addend) -> Problem:
    def attempt():
        t = _pick(rng, total)
        s = _pick(rng, addend)
        if s > t or s == t:
            return None
        return t, s

    t, s = _try(rng, attempt)
    ans = t - s
    if rng.random() < 0.5:
        prompt, speech = f"${s} + ? = {t}$", f"{say(s)} plus what number makes {say(t)}?"
    else:
        prompt, speech = f"$? + {s} = {t}$", f"What number plus {say(s)} makes {say(t)}?"
    return Problem(prompt=prompt, answer=str(ans), kind="int", lead="$? =$", speech=speech,
                   key=f"miss:{prompt}")


# ---------------------------------------------------------------------------
# word problems
# ---------------------------------------------------------------------------

_NAMES = [("Mia", "She"), ("Leo", "He"), ("Ana", "She"), ("Sam", "He"), ("Zoe", "She"), ("Noah", "He")]
_THINGS = ["stickers", "marbles", "blocks", "books", "cards", "crayons", "shells", "coins"]
_SHARE = [
    ("cookies", "kids", "kid"), ("stickers", "friends", "friend"), ("apples", "baskets", "basket"),
    ("crayons", "boxes", "box"), ("marbles", "bags", "bag"), ("pencils", "cups", "cup"),
    ("flowers", "vases", "vase"), ("grapes", "plates", "plate"),
]


@register("word_addsub")
def gen_word_addsub(rng, kind="mix", max=20) -> Problem:  # noqa: A002
    name, pron = rng.choice(_NAMES)
    other = rng.choice([n for n, _ in _NAMES if n != name])
    thing = rng.choice(_THINGS)
    k = rng.choice(["join", "separate", "compare"]) if kind == "mix" else kind
    if k in ("add", "join"):
        a = rng.randint(3, max - 3)
        b = rng.randint(2, max - a)
        text = f"{name} has {a} {thing}. {pron} gets {b} more. How many {thing} does {name} have now?"
        ans = a + b
    elif k in ("sub", "separate"):
        a = rng.randint(max // 2, max)
        b = rng.randint(2, a - 1)
        text = f"{name} has {a} {thing}. {pron} gives away {b}. How many {thing} are left?"
        ans = a - b
    else:
        a = rng.randint(max // 2, max)
        b = rng.randint(2, a - 1)
        text = f"{name} has {a} {thing}. {other} has {b}. How many more does {name} have?"
        ans = a - b
    return Problem(prompt=text, answer=str(ans), kind="int", lead="$=$", speech=text,
                   key=f"wd:{text}")


@register("share")
def gen_share(rng, divisors, quotient, mode="share") -> Problem:
    d = rng.choice(divisors)
    q = rng.randint(*quotient)
    item, plural, singular = rng.choice(_SHARE)
    m = rng.choice(["share", "groups"]) if mode == "mix" else mode
    if m == "share":
        total = d * q
        text = f"{total} {item} are shared equally among {d} {plural}. How many {item} does each {singular} get?"
        ans = q
    else:
        text = f"There are {d} {plural}. Each {singular} has {q} {item}. How many {item} in all?"
        ans = d * q
    return Problem(prompt=text, answer=str(ans), kind="int", lead="$=$", speech=text, key=f"share:{text}")


# ---------------------------------------------------------------------------
# multiplication / division
# ---------------------------------------------------------------------------


@register("equal_groups")
def gen_equal_groups(rng, rows, cols, mode="array") -> Problem:
    r = rng.randint(*rows)
    c = rng.randint(*cols)
    if mode == "array":
        return Problem(
            prompt=f"#grid(columns: 2, column-gutter: 3mm, align: horizon, dots({r}, {c}), [How many dots?])",
            answer=str(r * c), kind="int", lead="$=$",
            speech=f"There are {say(r)} rows with {say(c)} dots in each row. How many dots in all?",
            key=f"arr:{r}:{c}")
    terms = " + ".join([str(c)] * r)
    return Problem(prompt=f"${terms}$", answer=str(r * c), kind="int", lead="$=$",
                   speech=f"{say(c)}, added {say(r)} times", key=f"rep:{r}:{c}")


@register("mul")
def gen_mul(rng, tables, other, commute=True) -> Problem:
    t = rng.choice(tables)
    o = rng.randint(*other)
    a, b = (t, o) if (not commute or rng.random() < 0.5) else (o, t)
    return Problem(prompt=f"${a} times {b}$", answer=str(a * b), kind="int", lead="$=$",
                   speech=f"{say(a)} times {say(b)}", key=f"mul:{a}:{b}")


@register("div")
def gen_div(rng, divisors, quotient, remainder=False) -> Problem:
    d = rng.choice(divisors)
    q = rng.randint(*quotient)
    if remainder:
        r = rng.randint(1, d - 1)
        n = d * q + r
        return Problem(prompt=f"${n} div {d}$", answer=f"{q} R {r}", kind="int_rem",
                       lead="$=$", speech=f"{say(n)} divided by {say(d)}. Say the answer with a remainder.",
                       key=f"divr:{n}:{d}")
    n = d * q
    return Problem(prompt=f"${n} div {d}$", answer=str(q), kind="int", lead="$=$",
                   speech=f"{say(n)} divided by {say(d)}", key=f"div:{n}:{d}")


@register("missing_factor")
def gen_missing_factor(rng, tables, other) -> Problem:
    t = rng.choice(tables)
    o = rng.randint(*other)
    p = t * o
    if rng.random() < 0.5:
        prompt, speech = f"${t} times ? = {p}$", f"{say(t)} times what number makes {say(p)}?"
    else:
        prompt, speech = f"$? times {t} = {p}$", f"What number times {say(t)} makes {say(p)}?"
    return Problem(prompt=prompt, answer=str(o), kind="int", lead="$? =$", speech=speech,
                   key=f"mf:{prompt}")


# ---------------------------------------------------------------------------
# fractions
# ---------------------------------------------------------------------------


@register("frac_name")
def gen_frac_name(rng, dens, num=None) -> Problem:
    d = rng.choice(dens)
    lo, hi = (1, d - 1) if num is None else (num[0], min(num[1], d - 1))
    n = rng.randint(lo, hi)
    return Problem(
        prompt=f"#stack(dir: ttb, spacing: 1.2mm, fracbar({n}, {d}), text(size: 7.5pt)[What fraction is shaded?])",
        answer=_frac_tex(n, d), kind="frac", lead="$=$",
        speech=f"A bar is cut into {say(d)} equal parts and {say(n)} are shaded. What fraction is shaded?",
        key=f"fn:{n}/{d}")


@register("frac_compare")
def gen_frac_compare(rng, dens, same="den") -> Problem:
    if same == "den":
        def attempt():
            d = rng.choice(dens)
            if d < 3:
                return None
            n1, n2 = rng.sample(range(1, d), 2)
            return d, n1, d, n2
    else:
        def attempt():
            if len(dens) < 2:
                return None
            d1, d2 = rng.sample(list(dens), 2)
            top = rng.randint(1, min(d1, d2) - 1)
            return d1, top, d2, top
    d1, n1, d2, n2 = _try(rng, attempt)
    ans = "<" if n1 * d2 < n2 * d1 else ">"
    return Problem(
        prompt=f"#box[${n1}/{d1}$] #h(2.2em) #box[${n2}/{d2}$]",
        answer=ans, kind="symbol", lead="Write < or >",
        speech=f"Which is bigger, {say_frac(n1, d1)} or {say_frac(n2, d2)}?",
        key=f"fc:{n1}/{d1}:{n2}/{d2}")


@register("frac_numberline")
def gen_frac_numberline(rng, dens) -> Problem:
    d = rng.choice(dens)
    n = rng.randint(1, d - 1)
    return Problem(
        prompt=f"#stack(dir: ttb, spacing: 0.5mm, numline({d}, {n}), text(size: 7.5pt)[What fraction is the dot?])",
        answer=_frac_tex(n, d), kind="frac", lead="$=$",
        speech=f"A number line from zero to one is cut into {say(d)} equal jumps. The dot is at jump {say(n)}. What fraction is that?",
        key=f"fl:{n}/{d}")


@register("frac_equiv")
def gen_frac_equiv(rng, dens) -> Problem:
    options = []
    for b in dens:
        for k in range(2, 5):
            if b * k in dens:
                for a in range(1, b):
                    options.append((a, b, k))
    if not options:
        raise ValueError("no equivalent-fraction pairs for these denominators")
    a, b, k = rng.choice(options)
    return Problem(
        prompt=f"${a}/{b} = ?/{b * k}$", answer=str(a * k), kind="int", lead="$? =$",
        speech=f"{say_frac(a, b)} equals how many {say_frac(1, b * k)}s?",
        key=f"fe:{a}/{b}:{b * k}")


@register("frac_decompose")
def gen_frac_decompose(rng, dens) -> Problem:
    d = rng.choice(dens)
    n = rng.randint(2, min(5, d - 1)) if d > 2 else 2
    parts = " + ".join([f"1/{d}"] * (n - 1))
    return Problem(
        prompt=f"${n}/{d} = {parts} + ?$", answer=f"1/{d}", kind="frac", lead="$? =$",
        speech=f"{say_frac(n, d)} is made of unit pieces. What piece is missing?",
        key=f"fd:{n}/{d}")


@register("frac_of_set")
def gen_frac_of_set(rng, dens, total_max=24) -> Problem:
    d = rng.choice(dens)
    m = rng.randint(1, max(1, total_max // d))
    total = d * m
    return Problem(
        prompt=f"$1/{d}$ of ${total}$", answer=str(m), kind="int", lead="$=$",
        speech=f"What is {say_frac(1, d)} of {say(total)}?", key=f"fs:{d}:{total}")


@register("frac_add_like")
def gen_frac_add_like(rng, dens, op="add") -> Problem:
    def attempt():
        d = rng.choice(dens)
        if op == "add":
            if d < 3:
                return None
            n1 = rng.randint(1, d - 2)
            n2 = rng.randint(1, d - n1)
            return d, n1, n2
        n1 = rng.randint(2, d - 1) if d > 2 else None
        if n1 is None:
            return None
        n2 = rng.randint(1, n1 - 1)
        return d, n1, n2

    d, n1, n2 = _try(rng, attempt)
    if op == "add":
        return Problem(prompt=f"${n1}/{d} + {n2}/{d}$", answer=f"{n1 + n2}/{d}", kind="frac",
                       lead="$=$", speech=f"{say_frac(n1, d)} plus {say_frac(n2, d)}",
                       key=f"fa:{n1}+{n2}/{d}")
    return Problem(prompt=f"${n1}/{d} - {n2}/{d}$", answer=f"{n1 - n2}/{d}", kind="frac",
                   lead="$=$", speech=f"{say_frac(n1, d)} minus {say_frac(n2, d)}",
                   key=f"fa:{n1}-{n2}/{d}")


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------


def generate_one(generator: str, params: dict, rng: random.Random) -> Problem:
    if generator not in REGISTRY:
        raise KeyError(f"unknown generator {generator!r}")
    return REGISTRY[generator](rng, **params)


def generate(generator: str, params: dict, rng: random.Random, n: int,
             exclude: set[str] | None = None) -> list[Problem]:
    """Up to n distinct problems (distinct by key). May return fewer if the skill
    has a small problem space (e.g. only 22 problems exist for times 0 and 1)."""
    seen = set(exclude or ())
    out: list[Problem] = []
    tries = 0
    while len(out) < n and tries < 60 * max(1, n):
        tries += 1
        p = generate_one(generator, params, rng)
        if p.key in seen:
            continue
        seen.add(p.key)
        out.append(p)
    return out
