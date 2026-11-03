"""Problem generators for math skills.

Each generator takes a seeded `random.Random` plus the `params` table from the
curriculum TOML, and returns one `Problem`. Prompts are Typst markup, evaluated by
the templates with these helpers in scope: qbox, fracbar, numline, dots.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from fractions import Fraction

# ---------------------------------------------------------------------------
# data type
# ---------------------------------------------------------------------------


@dataclass
class Problem:
    prompt: str  # Typst markup shown to the child
    answer: str  # canonical answer string
    kind: str = "int"  # int | int_rem | frac | symbol | text
    lead: str = "$=$"  # Typst markup printed just before the answer box
    speech: str = ""  # what a parent reads aloud for an oral quiz
    key: str = ""  # identity for de-duplication
    prose: bool = False  # a sentence, not an expression: needs a bigger prompt box
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "prompt": self.prompt,
            "answer": self.answer,
            "kind": self.kind,
            "lead": self.lead,
            "speech": self.speech,
            "key": self.key,
            "prose": self.prose,
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

_ONES = [
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
]
_TENS = [
    "",
    "",
    "twenty",
    "thirty",
    "forty",
    "fifty",
    "sixty",
    "seventy",
    "eighty",
    "ninety",
]


def say(n: int) -> str:
    """English words for 0..999,999,999 (for parent read-aloud scripts)."""
    for size, name in ((1_000_000, "million"), (1000, "thousand")):
        if n >= size:
            big, r = divmod(n, size)
            return f"{say(big)} {name}" + (f" {say(r)}" if r else "")
    if n < 20:
        return _ONES[n]
    if n < 100:
        t, o = divmod(n, 10)
        return _TENS[t] + (f"-{_ONES[o]}" if o else "")
    h, r = divmod(n, 100)
    return f"{_ONES[h]} hundred" + (f" {say(r)}" if r else "")


_FRAC_NAMES = {
    2: "half",
    3: "third",
    4: "fourth",
    5: "fifth",
    6: "sixth",
    8: "eighth",
    10: "tenth",
}


def say_dec(x: str) -> str:
    """'3.25' -> 'three and twenty-five hundredths'."""
    whole, _, part = x.partition(".")
    if not part:
        return say(int(whole))
    name = {1: "tenth", 2: "hundredth", 3: "thousandth"}[len(part)]
    frac = say(int(part)) + f" {name}" + ("" if int(part) == 1 else "s")
    return frac if int(whole) == 0 else f"{say(int(whole))} and {frac}"


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
        answer=str(seq[hide]),
        kind="int",
        lead="$? =$",
        speech="Count by "
        + say(step)
        + "s: "
        + ", ".join(("what comes next" if s == "?" else say(int(s))) for s in shown)
        + ".",
        key=f"skip:{step}:{start}:{hide}",
    )


@register("place_value")
def gen_place_value(rng, mode="compose", digits=2) -> Problem:
    if digits == 2:
        n = rng.randint(11, 99)
        t, o = divmod(n, 10)
        if rng.random() < 0.5:
            return Problem(
                prompt=f"{t} tens and {o} ones",
                answer=str(n),
                kind="int",
                lead="$=$",
                speech=f"{say(t)} tens and {say(o)} ones. What number is that?",
                key=f"pv2c:{n}",
            )
        if rng.random() < 0.5:
            return Problem(
                prompt=f"How many tens in ${n}$?",
                answer=str(t),
                kind="int",
                lead="$=$",
                speech=f"How many tens are in {say(n)}?",
                key=f"pv2t:{n}",
            )
        return Problem(
            prompt=f"How many ones in ${n}$?",
            answer=str(o),
            kind="int",
            lead="$=$",
            speech=f"How many ones are in {say(n)}?",
            key=f"pv2o:{n}",
        )
    n = rng.randint(101, 999)
    h, rest = divmod(n, 100)
    t, o = divmod(rest, 10)
    r = rng.random()
    if r < 0.5:
        return Problem(
            prompt=f"{h} hundreds, {t} tens, {o} ones",
            answer=str(n),
            kind="int",
            lead="$=$",
            speech=f"{say(h)} hundreds, {say(t)} tens, {say(o)} ones. What number is that?",
            key=f"pv3c:{n}",
        )
    if r < 0.75:
        return Problem(
            prompt=f"How many hundreds in ${n}$?",
            answer=str(h),
            kind="int",
            lead="$=$",
            speech=f"How many hundreds are in {say(n)}?",
            key=f"pv3h:{n}",
        )
    return Problem(
        prompt=f"How many tens in the middle of ${n}$? (the tens digit)",
        answer=str(t),
        kind="int",
        lead="$=$",
        speech=f"What is the tens digit of {say(n)}?",
        key=f"pv3t:{n}",
    )


@register("compare")
def gen_compare(rng, range, allow_equal=False) -> Problem:
    lo, hi = range
    a = rng.randint(lo, hi)
    b = rng.randint(lo, hi)
    if not allow_equal:
        while b == a:
            b = rng.randint(lo, hi)
    ans = "<" if a < b else (">" if a > b else "=")
    return Problem(
        prompt=f"#box[${a}$] #h(2.2em) #box[${b}$]",
        answer=ans,
        kind="symbol",
        lead="Write < or >",
        speech=f"Which is bigger, {say(a)} or {say(b)}? Say less than or greater than.",
        key=f"cmp:{a}:{b}",
    )


# ---------------------------------------------------------------------------
# add / subtract
# ---------------------------------------------------------------------------


@register("add")
def gen_add(
    rng, a, b, max_sum=None, min_sum=0, equal=False, regroup="any", multiple_of=1
) -> Problem:
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
    return Problem(
        prompt=f"${x} + {y}$",
        answer=str(x + y),
        kind="int",
        lead="$=$",
        speech=f"{say(x)} plus {say(y)}",
        key=f"add:{x}:{y}",
    )


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
    return Problem(
        prompt=f"${x} - {y}$",
        answer=str(x - y),
        kind="int",
        lead="$=$",
        speech=f"{say(x)} minus {say(y)}",
        key=f"sub:{x}:{y}",
    )


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
        prompt, speech = (
            f"${s} + ? = {t}$",
            f"{say(s)} plus what number makes {say(t)}?",
        )
    else:
        prompt, speech = (
            f"$? + {s} = {t}$",
            f"What number plus {say(s)} makes {say(t)}?",
        )
    return Problem(
        prompt=prompt,
        answer=str(ans),
        kind="int",
        lead="$? =$",
        speech=speech,
        key=f"miss:{prompt}",
    )


# ---------------------------------------------------------------------------
# word problems
# ---------------------------------------------------------------------------

_NAMES = [
    ("Mia", "She"),
    ("Leo", "He"),
    ("Ana", "She"),
    ("Sam", "He"),
    ("Zoe", "She"),
    ("Noah", "He"),
]
_THINGS = [
    "stickers",
    "marbles",
    "blocks",
    "books",
    "cards",
    "crayons",
    "shells",
    "coins",
]
_SHARE = [
    ("cookies", "kids", "kid"),
    ("stickers", "friends", "friend"),
    ("apples", "baskets", "basket"),
    ("crayons", "boxes", "box"),
    ("marbles", "bags", "bag"),
    ("pencils", "cups", "cup"),
    ("flowers", "vases", "vase"),
    ("grapes", "plates", "plate"),
]


@register("word_addsub")
def gen_word_addsub(rng, kind="mix", max=20) -> Problem:
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
        text = (
            f"{name} has {a} {thing}. {pron} gives away {b}. How many {thing} are left?"
        )
        ans = a - b
    else:
        a = rng.randint(max // 2, max)
        b = rng.randint(2, a - 1)
        text = (
            f"{name} has {a} {thing}. {other} has {b}. How many more does {name} have?"
        )
        ans = a - b
    return Problem(
        prompt=text,
        answer=str(ans),
        kind="int",
        lead="$=$",
        speech=text,
        key=f"wd:{text}",
        prose=True,
    )


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
    return Problem(
        prompt=text,
        answer=str(ans),
        kind="int",
        lead="$=$",
        speech=text,
        key=f"share:{text}",
        prose=True,
    )


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
            answer=str(r * c),
            kind="int",
            lead="$=$",
            speech=f"There are {say(r)} rows with {say(c)} dots in each row. How many dots in all?",
            key=f"arr:{r}:{c}",
        )
    terms = " + ".join([str(c)] * r)
    return Problem(
        prompt=f"${terms}$",
        answer=str(r * c),
        kind="int",
        lead="$=$",
        speech=f"{say(c)}, added {say(r)} times",
        key=f"rep:{r}:{c}",
    )


@register("mul")
def gen_mul(rng, tables, other, commute=True) -> Problem:
    t = rng.choice(tables)
    o = rng.randint(*other)
    a, b = (t, o) if (not commute or rng.random() < 0.5) else (o, t)
    return Problem(
        prompt=f"${a} times {b}$",
        answer=str(a * b),
        kind="int",
        lead="$=$",
        speech=f"{say(a)} times {say(b)}",
        key=f"mul:{a}:{b}",
    )


@register("div")
def gen_div(rng, divisors, quotient, remainder=False) -> Problem:
    d = rng.choice(divisors)
    q = rng.randint(*quotient)
    if remainder:
        r = rng.randint(1, d - 1)
        n = d * q + r
        return Problem(
            prompt=f"${n} div {d}$",
            answer=f"{q} R {r}",
            kind="int_rem",
            lead="$=$",
            speech=f"{say(n)} divided by {say(d)}. Say the answer with a remainder.",
            key=f"divr:{n}:{d}",
        )
    n = d * q
    return Problem(
        prompt=f"${n} div {d}$",
        answer=str(q),
        kind="int",
        lead="$=$",
        speech=f"{say(n)} divided by {say(d)}",
        key=f"div:{n}:{d}",
    )


@register("missing_factor")
def gen_missing_factor(rng, tables, other) -> Problem:
    t = rng.choice(tables)
    o = rng.randint(*other)
    p = t * o
    if rng.random() < 0.5:
        prompt, speech = (
            f"${t} times ? = {p}$",
            f"{say(t)} times what number makes {say(p)}?",
        )
    else:
        prompt, speech = (
            f"$? times {t} = {p}$",
            f"What number times {say(t)} makes {say(p)}?",
        )
    return Problem(
        prompt=prompt,
        answer=str(o),
        kind="int",
        lead="$? =$",
        speech=speech,
        key=f"mf:{prompt}",
    )


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
        answer=_frac_tex(n, d),
        kind="frac",
        lead="$=$",
        speech=f"A bar is cut into {say(d)} equal parts and {say(n)} are shaded. What fraction is shaded?",
        key=f"fn:{n}/{d}",
    )


@register("frac_compare")
def gen_frac_compare(rng, dens, same="den") -> Problem:
    if same == "den":

        def attempt():
            d = rng.choice(dens)
            if d < 3:
                return None
            n1, n2 = rng.sample(range(1, d), 2)
            return d, n1, d, n2
    elif same == "num":

        def attempt():
            if len(dens) < 2:
                return None
            d1, d2 = rng.sample(list(dens), 2)
            top = rng.randint(1, min(d1, d2) - 1)
            return d1, top, d2, top
    else:

        def attempt():
            d1, d2 = rng.sample(list(dens), 2)
            n1, n2 = rng.randint(1, d1 - 1), rng.randint(1, d2 - 1)
            if n1 == n2 or n1 * d2 == n2 * d1:
                return None
            return d1, n1, d2, n2

    d1, n1, d2, n2 = _try(rng, attempt)
    ans = "<" if n1 * d2 < n2 * d1 else ">"
    return Problem(
        prompt=f"#box[${n1}/{d1}$] #h(2.2em) #box[${n2}/{d2}$]",
        answer=ans,
        kind="symbol",
        lead="Write < or >",
        speech=f"Which is bigger, {say_frac(n1, d1)} or {say_frac(n2, d2)}?",
        key=f"fc:{n1}/{d1}:{n2}/{d2}",
    )


@register("frac_numberline")
def gen_frac_numberline(rng, dens) -> Problem:
    d = rng.choice(dens)
    n = rng.randint(1, d - 1)
    return Problem(
        prompt=f"#stack(dir: ttb, spacing: 0.5mm, numline({d}, {n}), text(size: 7.5pt)[What fraction is the dot?])",
        answer=_frac_tex(n, d),
        kind="frac",
        lead="$=$",
        speech=f"A number line from zero to one is cut into {say(d)} equal jumps. The dot is at jump {say(n)}. What fraction is that?",
        key=f"fl:{n}/{d}",
    )


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
        prompt=f"${a}/{b} = ?/{b * k}$",
        answer=str(a * k),
        kind="int",
        lead="$? =$",
        speech=f"{say_frac(a, b)} equals how many {say_frac(1, b * k)}s?",
        key=f"fe:{a}/{b}:{b * k}",
    )


@register("frac_decompose")
def gen_frac_decompose(rng, dens) -> Problem:
    d = rng.choice(dens)
    n = rng.randint(2, min(5, d - 1)) if d > 2 else 2
    parts = " + ".join([f"1/{d}"] * (n - 1))
    return Problem(
        prompt=f"${n}/{d} = {parts} + ?$",
        answer=f"1/{d}",
        kind="frac",
        lead="$? =$",
        speech=f"{say_frac(n, d)} is made of unit pieces. What piece is missing?",
        key=f"fd:{n}/{d}",
    )


@register("frac_of_set")
def gen_frac_of_set(rng, dens, total_max=24) -> Problem:
    d = rng.choice(dens)
    m = rng.randint(1, max(1, total_max // d))
    total = d * m
    return Problem(
        prompt=f"$1/{d}$ of ${total}$",
        answer=str(m),
        kind="int",
        lead="$=$",
        speech=f"What is {say_frac(1, d)} of {say(total)}?",
        key=f"fs:{d}:{total}",
    )


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
        return Problem(
            prompt=f"${n1}/{d} + {n2}/{d}$",
            answer=f"{n1 + n2}/{d}",
            kind="frac",
            lead="$=$",
            speech=f"{say_frac(n1, d)} plus {say_frac(n2, d)}",
            key=f"fa:{n1}+{n2}/{d}",
        )
    return Problem(
        prompt=f"${n1}/{d} - {n2}/{d}$",
        answer=f"{n1 - n2}/{d}",
        kind="frac",
        lead="$=$",
        speech=f"{say_frac(n1, d)} minus {say_frac(n2, d)}",
        key=f"fa:{n1}-{n2}/{d}",
    )


# ---------------------------------------------------------------------------
# kindergarten counting
# ---------------------------------------------------------------------------


@register("count_dots")
def gen_count_dots(rng, count) -> Problem:
    n = rng.randint(*count)
    return Problem(
        prompt=f"#grid(columns: 2, column-gutter: 3mm, align: horizon, countdots({n}), [How many?])",
        answer=str(n),
        kind="int",
        lead="$=$",
        speech=f"Point to each dot and count. How many dots? (There are {say(n)}.)",
        key=f"cnt:{n}",
    )


@register("neighbor")
def gen_neighbor(rng, range, mode="after") -> Problem:
    m = rng.choice(["after", "before"]) if mode == "mix" else mode
    lo, hi = range
    n = rng.randint(lo + (1 if m == "before" else 0), hi - (1 if m == "after" else 0))
    ans = n + 1 if m == "after" else n - 1
    return Problem(
        prompt=f"Just {m} ${n}$",
        answer=str(ans),
        kind="int",
        lead="$=$",
        speech=f"What number comes just {m} {say(n)}?",
        key=f"nb:{m}:{n}",
    )


# ---------------------------------------------------------------------------
# place value, rounding, money
# ---------------------------------------------------------------------------


def _n(x: int) -> str:
    """A whole number for a Typst math prompt, with thousands commas from 10,000 up."""
    return f'"{x:,}"' if x >= 10_000 else str(x)


_PLACES = [
    "ones",
    "tens",
    "hundreds",
    "thousands",
    "ten thousands",
    "hundred thousands",
    "millions",
    "ten millions",
    "hundred millions",
]


@register("digit_value")
def gen_digit_value(rng, digits) -> Problem:
    def attempt():
        k = rng.randint(*digits)
        n = rng.randint(10 ** (k - 1), 10**k - 1)
        s = str(n)
        pos = rng.randrange(len(s) - 1)
        d = s[pos]
        if d == "0" or s.count(d) > 1:
            return None
        return n, d, len(s) - 1 - pos

    n, d, place = _try(rng, attempt)
    value = int(d) * 10**place
    return Problem(
        prompt=f"In ${_n(n)}$, the value of the ${d}$",
        answer=str(value),
        kind="int",
        lead="$=$",
        speech=f"In the number {say(n)}, what is the {say(int(d))} worth? (It is in the {_PLACES[place]} place.)",
        key=f"dv:{n}:{d}",
    )


@register("round")
def gen_round(rng, places, range) -> Problem:
    def attempt():
        p = rng.choice(places)
        n = rng.randint(*range)
        if n % p == 0 or n < p:
            return None
        return p, n

    p, n = _try(rng, attempt)
    ans = (n + p // 2) // p * p
    name = {10: "ten", 100: "hundred", 1000: "thousand", 10_000: "ten thousand"}[p]
    return Problem(
        prompt=f"Round ${_n(n)}$ to the nearest {name}",
        answer=str(ans),
        kind="int",
        lead="$=$",
        speech=f"Round {say(n)} to the nearest {name}.",
        key=f"rnd:{n}:{p}",
    )


_COINS = {"penny": 1, "nickel": 5, "dime": 10, "quarter": 25}
_COIN_PLURAL = {
    "penny": "pennies",
    "nickel": "nickels",
    "dime": "dimes",
    "quarter": "quarters",
}


@register("coins")
def gen_coins(rng, coins, max_each=4) -> Problem:
    def attempt():
        kinds = rng.sample(coins, rng.randint(2, min(3, len(coins))))
        counts = {c: rng.randint(1, max_each) for c in kinds}
        total = sum(_COINS[c] * k for c, k in counts.items())
        return (counts, total) if total < 100 else None

    counts, total = _try(rng, attempt)
    order = sorted(counts, key=lambda c: -_COINS[c])
    parts = [f"{counts[c]} {c if counts[c] == 1 else _COIN_PLURAL[c]}" for c in order]
    text = ", ".join(parts)
    return Problem(
        prompt=f"{text}: how many cents?",
        answer=str(total),
        kind="int",
        lead="$=$",
        speech=f"{text}. How many cents is that?",
        key=f"coin:{text}",
        prose=True,
    )


# ---------------------------------------------------------------------------
# multi-digit operations, order of operations
# ---------------------------------------------------------------------------


@register("mul_multi")
def gen_mul_multi(rng, a, b) -> Problem:
    x, y = rng.randint(*a), rng.randint(*b)
    return Problem(
        prompt=f"${_n(x)} times {_n(y)}$",
        answer=str(x * y),
        kind="int",
        lead="$=$",
        speech=f"{say(x)} times {say(y)}",
        key=f"mm:{x}:{y}",
    )


@register("div_multi")
def gen_div_multi(rng, divisor, quotient, remainder=False) -> Problem:
    d, q = rng.randint(*divisor), rng.randint(*quotient)
    r = rng.randint(1, d - 1) if remainder else 0
    n = d * q + r
    return Problem(
        prompt=f"${_n(n)} div {d}$",
        answer=f"{q} R {r}" if remainder else str(q),
        kind="int_rem" if remainder else "int",
        lead="$=$",
        speech=f"{say(n)} divided by {say(d)}"
        + (". Say the answer with a remainder." if remainder else ""),
        key=f"dm:{n}:{d}",
    )


_OPS_FORMS = {
    "a+b*c": lambda a, b, c: a + b * c,
    "a-b*c": lambda a, b, c: a - b * c,
    "b*c+a": lambda a, b, c: b * c + a,
    "a+c/b": lambda a, b, c: a + c // b,
    "(a+b)*c": lambda a, b, c: (a + b) * c,
    "(a-b)*c": lambda a, b, c: (a - b) * c,
}


@register("order_ops")
def gen_order_ops(rng, parens=False) -> Problem:
    forms = list(_OPS_FORMS) if parens else ["a+b*c", "a-b*c", "b*c+a", "a+c/b"]

    def attempt():
        a, b, c = rng.randint(2, 12), rng.randint(2, 9), rng.randint(2, 9)
        form = rng.choice(forms)
        if form == "a+c/b":
            c = b * rng.randint(1, 9)
        val = _OPS_FORMS[form](a, b, c)
        if val < 0:
            return None
        expr = form.replace("a", str(a)).replace("b", str(b)).replace("c", str(c))
        return expr, val

    expr, val = _try(rng, attempt)
    shown = (
        expr.replace("*", " times ")
        .replace("/", " div ")
        .replace("+", " + ")
        .replace("-", " - ")
    )
    spoken = (
        expr.replace("*", " times ")
        .replace("/", " divided by ")
        .replace("+", " plus ")
        .replace("-", " minus ")
    )
    spoken = spoken.replace("(", "open bracket ").replace(")", " close bracket")
    return Problem(
        prompt=f"${shown}$",
        answer=str(val),
        kind="int",
        lead="$=$",
        speech=f"Write this down and work it out: {spoken}. Multiply and divide before adding and subtracting.",
        key=f"oo:{expr}",
    )


# ---------------------------------------------------------------------------
# measurement: area, perimeter, volume
# ---------------------------------------------------------------------------

_UNITS = ["cm", "m", "in", "ft"]


@register("rect_measure")
def gen_rect_measure(rng, side, mode="area") -> Problem:
    m = rng.choice(["area", "perimeter", "missing"]) if mode == "mix" else mode
    l, w = rng.randint(*side), rng.randint(*side)
    u = rng.choice(_UNITS)
    if m == "area":
        text = f"A rectangle is {l} {u} long and {w} {u} wide. What is its area in square {u}?"
        ans = l * w
    elif m == "perimeter":
        text = f"A rectangle is {l} {u} long and {w} {u} wide. What is its perimeter in {u}?"
        ans = 2 * (l + w)
    else:
        text = f"A rectangle has an area of {l * w} square {u}. It is {l} {u} long. How wide is it?"
        ans = w
    return Problem(
        prompt=text,
        answer=str(ans),
        kind="int",
        lead="$=$",
        speech=text,
        key=f"rect:{text}",
        prose=True,
    )


@register("volume")
def gen_volume(rng, side) -> Problem:
    l, w, h = (rng.randint(*side) for _ in range(3))
    u = rng.choice(_UNITS)
    text = f"A box is {l} {u} long, {w} {u} wide and {h} {u} tall. What is its volume in cubic {u}?"
    return Problem(
        prompt=text,
        answer=str(l * w * h),
        kind="int",
        lead="$=$",
        speech=text,
        key=f"vol:{l}:{w}:{h}:{u}",
        prose=True,
    )


# ---------------------------------------------------------------------------
# decimals
# ---------------------------------------------------------------------------


def _dec(units: int, places: int) -> str:
    """An integer count of 10^-places as a decimal string: (325, 2) -> '3.25', (230, 2) -> '2.3'."""
    v = Decimal(units).scaleb(-places).normalize()
    return format(v, "f") if v else "0"


@register("dec_frac")
def gen_dec_frac(rng, dens, mode="to_dec") -> Problem:
    m = rng.choice(["to_dec", "to_frac"]) if mode == "mix" else mode
    d = rng.choice(dens)
    n = rng.randint(1, d - 1)
    if n % 10 == 0 and d == 100:
        n += 1
    places = len(str(d)) - 1
    x = _dec(n, places)
    if m == "to_dec":
        return Problem(
            prompt=f"${n}/{d}$ as a decimal",
            answer=x,
            kind="dec",
            lead="$=$",
            speech=f"Write {say_frac(n, d) if d == 10 else say(n) + ' hundredths'} as a decimal.",
            key=f"df:{n}/{d}",
        )
    return Problem(
        prompt=f"${x}$ as a fraction",
        answer=f"{n}/{d}",
        kind="frac",
        lead="$=$",
        speech=f"Write {say_dec(x)} as a fraction.",
        key=f"fd:{x}",
    )


@register("dec_compare")
def gen_dec_compare(rng, places, whole=(0, 9)) -> Problem:
    def attempt():
        p1, p2 = rng.choice(places), rng.choice(places)
        w = rng.randint(*whole)
        a = _dec(w * 10**p1 + rng.randint(1, 10**p1 - 1), p1)
        b = _dec(w * 10**p2 + rng.randint(1, 10**p2 - 1), p2)
        return (a, b) if Decimal(a) != Decimal(b) else None

    a, b = _try(rng, attempt)
    return Problem(
        prompt=f"#box[${a}$] #h(2.2em) #box[${b}$]",
        answer="<" if Decimal(a) < Decimal(b) else ">",
        kind="symbol",
        lead="Write < or >",
        speech=f"Which is bigger, {say_dec(a)} or {say_dec(b)}?",
        key=f"dc:{a}:{b}",
    )


@register("dec_round")
def gen_dec_round(rng, places, to, whole=(0, 99)) -> Problem:
    def attempt():
        n = rng.randint(whole[0] * 10**places + 1, (whole[1] + 1) * 10**places - 1)
        if n % 10 ** (places - to) == 0:
            return None
        return n

    n = _try(rng, attempt)
    step = 10 ** (places - to)
    q, r = divmod(n, step)
    rounded = (q + (1 if r * 2 >= step else 0)) * step
    x, ans = _dec(n, places), _dec(rounded // step, to)
    name = {0: "whole number", 1: "tenth", 2: "hundredth"}[to]
    return Problem(
        prompt=f"Round ${x}$ to the nearest {name}",
        answer=ans,
        kind="dec",
        lead="$=$",
        speech=f"Round {say_dec(x)} to the nearest {name}.",
        key=f"dr:{x}:{to}",
    )


@register("dec_addsub")
def gen_dec_addsub(rng, places, whole, op="add") -> Problem:
    o = rng.choice(["add", "sub"]) if op == "mix" else op
    p1, p2 = rng.choice(places), rng.choice(places)
    a = rng.randint(whole[0] * 10**p1 + 1, (whole[1] + 1) * 10**p1 - 1)
    b = rng.randint(whole[0] * 10**p2 + 1, (whole[1] + 1) * 10**p2 - 1)
    x, y = Decimal(_dec(a, p1)), Decimal(_dec(b, p2))
    if o == "sub" and y > x:
        x, y = y, x
    val = x + y if o == "add" else x - y
    sym, word = ("+", "plus") if o == "add" else ("-", "minus")
    return Problem(
        prompt=f"${x} {sym} {y}$",
        answer=format(val.normalize(), "f") if val else "0",
        kind="dec",
        lead="$=$",
        speech=f"{say_dec(str(x))} {word} {say_dec(str(y))}. Line up the decimal points.",
        key=f"da:{x}{sym}{y}",
    )


@register("dec_mul")
def gen_dec_mul(rng, places, whole, by="whole") -> Problem:
    p = rng.choice(places)
    x = Decimal(_dec(rng.randint(whole[0] * 10**p + 1, (whole[1] + 1) * 10**p - 1), p))
    if by == "whole":
        y = Decimal(rng.randint(2, 9))
    else:
        y = Decimal(_dec(rng.randint(1, 9), 1))
    val = (x * y).normalize()
    return Problem(
        prompt=f"${x} times {y}$",
        answer=format(val, "f"),
        kind="dec",
        lead="$=$",
        speech=f"{say_dec(str(x))} times {say_dec(str(y))}",
        key=f"dmu:{x}:{y}",
    )


@register("dec_div")
def gen_dec_div(rng, divisor, quotient, places=1) -> Problem:
    d = rng.randint(*divisor)
    q = Decimal(
        _dec(
            rng.randint(quotient[0] * 10**places + 1, quotient[1] * 10**places), places
        )
    )
    n = q * d
    return Problem(
        prompt=f"${n} div {d}$",
        answer=format(q.normalize(), "f"),
        kind="dec",
        lead="$=$",
        speech=f"{say_dec(str(n))} divided by {say(d)}",
        key=f"ddv:{n}:{d}",
    )


# ---------------------------------------------------------------------------
# fractions, grades 4 and 5
# ---------------------------------------------------------------------------


def _frac_str(f: Fraction) -> str:
    return str(f.numerator) if f.denominator == 1 else f"{f.numerator}/{f.denominator}"


@register("frac_mixed_addsub")
def gen_frac_mixed_addsub(rng, dens, whole=(1, 5), op="add") -> Problem:
    o = rng.choice(["add", "sub"]) if op == "mix" else op
    d = rng.choice(dens)
    a = rng.randint(*whole) * d + rng.randint(1, d - 1)  # in d-ths, so 6/4 stays 1 2/4
    b = rng.randint(*whole) * d + rng.randint(1, d - 1)
    if o == "sub" and b > a:
        a, b = b, a
    if a == b:
        b -= 1
    val = a + b if o == "add" else a - b

    def mixed(n: int) -> str:
        w, r = divmod(n, d)
        return f"{w} {r}/{d}" if r and w else (f"{r}/{d}" if r else str(w))

    def spoken(n: int) -> str:
        w, r = divmod(n, d)
        part = say_frac(r, d) if r else ""
        return f"{say(w)} and {part}" if w and r else (part or say(w))

    sym, word = ("+", "plus") if o == "add" else ("-", "minus")
    return Problem(
        prompt=f"${mixed(a)} {sym} {mixed(b)}$",
        answer=mixed(val),
        kind="frac",
        lead="$=$",
        speech=f"{spoken(a)} {word} {spoken(b)}. A mixed number or a fraction is fine.",
        key=f"fm:{a}{sym}{b}/{d}",
    )


@register("frac_add_unlike")
def gen_frac_add_unlike(rng, dens, op="add") -> Problem:
    def attempt():
        d1, d2 = rng.sample(list(dens), 2)
        a = Fraction(rng.randint(1, d1 - 1), d1)
        b = Fraction(rng.randint(1, d2 - 1), d2)
        o = rng.choice(["add", "sub"]) if op == "mix" else op
        if o == "sub" and b >= a:
            return None
        return a, b, o

    a, b, o = _try(rng, attempt)
    val = a + b if o == "add" else a - b
    sym, word = ("+", "plus") if o == "add" else ("-", "minus")
    return Problem(
        prompt=f"${_frac_str(a)} {sym} {_frac_str(b)}$",
        answer=_frac_str(val),
        kind="frac",
        lead="$=$",
        speech=f"{say_frac(a.numerator, a.denominator)} {word} {say_frac(b.numerator, b.denominator)}",
        key=f"fu:{a}{sym}{b}",
    )


@register("frac_times_whole")
def gen_frac_times_whole(rng, dens, whole) -> Problem:
    d = rng.choice(dens)
    f = Fraction(rng.randint(1, d - 1), d)
    w = rng.randint(*whole)
    return Problem(
        prompt=f"${w} times {f.numerator}/{f.denominator}$",
        answer=_frac_str(f * w),
        kind="frac",
        lead="$=$",
        speech=f"{say(w)} times {say_frac(f.numerator, f.denominator)}",
        key=f"ftw:{w}:{f}",
    )


@register("frac_div_unit")
def gen_frac_div_unit(rng, dens, whole) -> Problem:
    d, w = rng.choice(dens), rng.randint(*whole)
    if rng.random() < 0.5:
        return Problem(
            prompt=f"$1/{d} div {w}$",
            answer=f"1/{d * w}",
            kind="frac",
            lead="$=$",
            speech=f"{say_frac(1, d)} divided by {say(w)}",
            key=f"fdu:1/{d}:{w}",
        )
    return Problem(
        prompt=f"${w} div 1/{d}$",
        answer=str(w * d),
        kind="int",
        lead="$=$",
        speech=f"{say(w)} divided by {say_frac(1, d)}. How many {say_frac(1, d)}s fit in {say(w)}?",
        key=f"fdu:{w}:1/{d}",
    )


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------


def generate_one(generator: str, params: dict, rng: random.Random) -> Problem:
    if generator not in REGISTRY:
        raise KeyError(f"unknown generator {generator!r}")
    return REGISTRY[generator](rng, **params)


def generate(
    generator: str,
    params: dict,
    rng: random.Random,
    n: int,
    exclude: set[str] | None = None,
) -> list[Problem]:
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
