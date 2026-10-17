"""Pattern structure generators. Each returns a GenPattern whose lines hold gold programs.

Labels are left empty here; the renderer fills them in the style it writes them.
Header and note lines carry their own fixed English text.
"""
from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field

from ..schema import (
    IntoOne,
    LineKind,
    LineProgram,
    Repeat,
    Start,
    Together,
    TurningChain,
    Work,
    WorkRest,
)

TRAIN_SHAPES = ["sphere", "cylinder", "rectangle", "triangle", "trapezoid", "mixed", "two_part"]
EVAL_ONLY_SHAPES = ["cone"]

_ADJ = ["Tiny", "Chunky", "Sleepy", "Little", "Cozy", "Happy", "Mini", "Lucky", "Sunny", "Plain", "Speckled", "Pocket", "Round", "Soft", "Striped"]
_NOUN_ROUND = ["Ball", "Bean", "Pea", "Egg", "Blob", "Bun", "Planet", "Moon", "Berry", "Pebble", "Acorn", "Head"]
_NOUN_TUBE = ["Tube", "Cactus", "Leg", "Tail", "Pillar", "Sleeve", "Worm", "Candle", "Arm"]
_NOUN_FLAT = ["Washcloth", "Coaster", "Dishcloth", "Scarf Panel", "Bookmark", "Placemat", "Swatch", "Pot Holder", "Mug Rug"]
_NOUN_TRI = ["Bunting Flag", "Kerchief", "Pennant", "Shawl Wedge", "Ear"]
_NOUN_CONE = ["Gnome Hat", "Carrot", "Party Hat", "Horn", "Beak", "Tree"]


@dataclass
class GenLine:
    program: LineProgram
    text: str | None = None  # fixed text for header/note lines
    meta: dict = field(default_factory=dict)  # render hints


@dataclass
class GenPattern:
    pid: str
    shape: str
    title: str
    construction: str  # "spiral" | "joined" | "rows"
    lines: list[GenLine]

    def copy(self) -> "GenPattern":
        return copy.deepcopy(self)


def _note(text: str) -> GenLine:
    return GenLine(LineProgram(kind=LineKind.NOTE), text=text)


def _counted(kind: str, ops, stated, start: Start | None = None, rng_range=None, **meta) -> GenLine:
    rs, re_ = rng_range if rng_range else (None, None)
    return GenLine(
        LineProgram(kind=kind, ops=list(ops), stated_count=stated, start=start or Start(), range_start=rs, range_end=re_),
        meta=meta,
    )


def _header(rng: random.Random, title: str, construction: str) -> list[GenLine]:
    lines = [_note(title)]
    how = {
        "spiral": rng.choice(["Worked in continuous spiral rounds.", "Work in a spiral; do not join rounds.", "Worked in spiral rounds, use a stitch marker."]),
        "joined": rng.choice(["Worked in joined rounds.", "Each round is worked in joined rounds: join with a sl st to the first st."]),
        "rows": rng.choice(["Worked flat in rows.", "Worked in rows, turning at the end of each row.", ""]),
    }[construction]
    terms = rng.choice(["US terms.", "Written in US terms.", "US crochet terms used throughout."])
    if rng.random() < 0.5 and how:
        lines.append(_note(f"{terms} {how}"))
    else:
        lines.append(_note(terms))
        if how:
            lines.append(_note(how))
    if rng.random() < 0.4:
        flat = construction == "rows"
        options = [
            "You will need: DK cotton yarn, 3.5 mm hook, scissors.",
            "Abbreviations: sc = single crochet, inc = 2 sc in the same st, dec = sc2tog.",
        ] + (
            ["Materials: worsted weight cotton, 5 mm hook, tapestry needle.", "Gauge is not critical for this project."]
            if flat
            else ["Materials: worsted weight yarn, 4 mm hook, stuffing, tapestry needle.", "Materials: aran yarn in two colors, 5 mm hook, 9 mm safety eyes, fiberfill."]
        )
        lines.append(_note(rng.choice(options)))
    return lines


def _maybe(rng, p, text) -> list[GenLine]:
    return [_note(text)] if rng.random() < p else []


def _around_or(rng: random.Random, times: int, p_around: float = 0.35) -> int | None:
    return None if rng.random() < p_around else times


def _even_rounds(rng: random.Random, count: int, n: int, kind: str = "round") -> list[GenLine]:
    """n plain rounds of `count` stitches, as one range, several ranges, or single lines."""
    out: list[GenLine] = []
    remaining = n
    while remaining > 0:
        if remaining >= 2 and rng.random() < 0.7:
            size = rng.randint(2, remaining)
        else:
            size = 1
        ops = [WorkRest(stitch="sc")] if rng.random() < 0.8 else [Work(stitch="sc", n=count)]
        out.append(_counted(kind, ops, count, range_len=size))
        remaining -= size
    return out


def _inc_round(rng: random.Random, k: int, i: int) -> list:
    """Round i of a k-start flat circle: (sc i-2, inc) x k, possibly offset."""
    base = i - 2
    if base == 0:
        return [Repeat(times=_around_or(rng, k), body=[IntoOne(stitch="sc", k=2)])]
    if i >= 4 and rng.random() < 0.3:
        a = base // 2
        b = base - a
        ops: list = []
        if a:
            ops.append(Work(stitch="sc", n=a))
        ops.append(IntoOne(stitch="sc", k=2))
        ops.append(Repeat(times=k - 1, body=[Work(stitch="sc", n=base), IntoOne(stitch="sc", k=2)]))
        if b:
            ops.append(Work(stitch="sc", n=b))
        return ops
    return [Repeat(times=_around_or(rng, k), body=[Work(stitch="sc", n=base), IntoOne(stitch="sc", k=2)])]


def _dec_round(rng: random.Random, k: int, j: int) -> list:
    """Decrease round making k*j stitches from k*(j+1): (sc j-1, dec) x k."""
    base = j - 1
    body = [Together(stitch="sc", k=2)] if base == 0 else [Work(stitch="sc", n=base), Together(stitch="sc", k=2)]
    return [Repeat(times=_around_or(rng, k, 0.3), body=body)]


def _circle(rng: random.Random, k: int, n_inc: int, joined: bool) -> tuple[list[GenLine], int]:
    """Magic ring start plus n_inc increase rounds. Returns (lines, final count)."""
    lines = [_counted("round", [Work(stitch="sc", n=k)], k, start=Start(type="magic_ring"))]
    for i in range(2, n_inc + 2):
        lines.append(_counted("round", _inc_round(rng, k, i), k * i))
    if joined:
        for gl in lines[1:]:
            gl.program.ops.insert(0, TurningChain(n=1))
            gl.meta["joined"] = True
        lines[0].meta["joined"] = True
    return lines, k * (n_inc + 1)


def _apply_ranges(lines: list[GenLine], first_row: int) -> list[GenLine]:
    """Assign row numbers (range_start/range_end) in order, from meta['range_len']."""
    n = first_row
    for gl in lines:
        p = gl.program
        if p.kind in (LineKind.ROW, LineKind.ROUND, LineKind.UNSUPPORTED) and gl.text is None:
            size = gl.meta.pop("range_len", 1)
            gl.meta["row_no"] = n
            if size > 1:
                p.range_start, p.range_end = n, n + size - 1
            n += size
    return lines


def _lace_pair(count: int) -> list[GenLine]:
    """Two chain-space rounds that v1 can't check; both state the count."""
    a = GenLine(LineProgram(kind=LineKind.UNSUPPORTED, stated_count=count, unsupported_reason="chain spaces (lace)"), meta={"lace": "open"})
    b = GenLine(LineProgram(kind=LineKind.UNSUPPORTED, stated_count=count, unsupported_reason="works into chain spaces"), meta={"lace": "close"})
    return [a, b]


# ---------------------------------------------------------------------------
# Shapes
# ---------------------------------------------------------------------------


def sphere(rng: random.Random, pid: str) -> GenPattern:
    k = rng.choice([5, 6, 6, 6, 7, 8])
    joined = rng.random() < 0.25
    n_inc = rng.randint(3, 6)
    title = f"{rng.choice(_ADJ)} {rng.choice(_NOUN_ROUND)}"
    construction = "joined" if joined else "spiral"
    body, count = _circle(rng, k, n_inc, joined)
    body += _even_rounds(rng, count, rng.randint(1, 7))
    if joined:
        for gl in body[n_inc + 1 :]:
            gl.program.ops.insert(0, TurningChain(n=1))
            gl.meta["joined"] = True
    body += _maybe(rng, 0.5, f"Place safety eyes between Rnd {n_inc + 2} and {n_inc + 3}, about {k} sts apart.")
    for j in range(n_inc, 0, -1):
        if j == n_inc - 1 and rng.random() < 0.6:
            body += [_note(rng.choice(["Begin stuffing.", "Stuff firmly.", "Start stuffing, adding more as you go."]))]
        gl = _counted("round", _dec_round(rng, k, j), k * j)
        if joined:
            gl.program.ops.insert(0, TurningChain(n=1))
            gl.meta["joined"] = True
        body.append(gl)
    body += _maybe(rng, 0.8, rng.choice(["FO, leave a long tail.", "Fasten off, weave the tail through the front loops and pull tight.", "Fasten off and weave in ends."]))
    lines = _header(rng, title, construction) + _apply_ranges(body, 1)
    return GenPattern(pid, "sphere", title, construction, lines)


def cylinder(rng: random.Random, pid: str) -> GenPattern:
    k = rng.choice([5, 6, 6, 7, 8])
    joined = rng.random() < 0.2
    n_inc = rng.randint(1, 4)
    title = f"{rng.choice(_ADJ)} {rng.choice(_NOUN_TUBE)}"
    construction = "joined" if joined else "spiral"
    body, count = _circle(rng, k, n_inc, joined)
    tail = _even_rounds(rng, count, rng.randint(4, 14))
    if rng.random() < 0.35:
        cut = rng.randint(1, max(1, len(tail) - 1))
        tail.insert(cut, _note(rng.choice(["Change to color B.", "Switch to the second color.", "Place a stitch marker here for the arm."])))
    if rng.random() < 0.12:
        tail[1:1] = _lace_pair(count)
    if rng.random() < 0.25:
        tail.insert(0, _note("Work the next round in BLO."))
    if joined:
        for gl in tail:
            if gl.text is None and gl.program.kind == LineKind.ROUND:
                gl.program.ops.insert(0, TurningChain(n=1))
                gl.meta["joined"] = True
    body += tail
    body += _maybe(rng, 0.7, rng.choice(["FO, leave a long tail for sewing.", "Fasten off. Do not stuff.", "Stuff lightly and FO."]))
    lines = _header(rng, title, construction) + _apply_ranges(body, 1)
    return GenPattern(pid, "cylinder", title, construction, lines)


def cone(rng: random.Random, pid: str) -> GenPattern:
    """Eval-only shape: slow increases, +per every other round."""
    per = rng.choice([3, 4])
    count = per * 2
    title = f"{rng.choice(_ADJ)} {rng.choice(_NOUN_CONE)}"
    body = [_counted("round", [Work(stitch="sc", n=count)], count, start=Start(type="magic_ring"))]
    for _ in range(rng.randint(3, 7)):
        body.append(_counted("round", [WorkRest(stitch="sc")], count, range_len=rng.choice([1, 1, 2])))
        a = count // per - 1
        ops = [Repeat(times=_around_or(rng, per), body=[Work(stitch="sc", n=a), IntoOne(stitch="sc", k=2)])]
        count += per
        body.append(_counted("round", ops, count))
    body += _even_rounds(rng, count, rng.randint(1, 3))
    body += _maybe(rng, 0.7, "Stuff lightly. FO and leave a tail for sewing.")
    lines = _header(rng, title, "spiral") + _apply_ranges(body, 1)
    return GenPattern(pid, "cone", title, "spiral", lines)


def _turn_spec(rng: random.Random, stitch: str) -> tuple[int, bool]:
    if stitch == "sc":
        return 1, False
    if stitch == "hdc":
        return rng.choice([(2, False), (1, False), (2, True)])
    return rng.choice([(3, True), (3, True), (2, False)])


def _row_start(rng, stitch, width, counts, same_line_chain: bool) -> tuple[list[GenLine], GenLine]:
    """Foundation chain (own line or same line) and Row 1 working into it."""
    skip = {"sc": 1, "hdc": 2, "dc": 3}[stitch]
    chain = width + skip - (1 if counts else 0)
    start = Start(skip_chains=skip, skipped_count_as_stitch=counts)
    if same_line_chain:
        start = Start(type="chain", chain_count=chain, skip_chains=skip, skipped_count_as_stitch=counts)
        return [], _counted("row", [WorkRest(stitch=stitch)], width, start=start, row1=True)
    found = GenLine(LineProgram(kind=LineKind.FOUNDATION, start=Start(type="chain", chain_count=chain)))
    return [found], _counted("row", [WorkRest(stitch=stitch)], width, start=start, row1=True)


def _turned(ops: list, tc: tuple[int, bool], at_end: bool) -> list:
    n, counts = tc
    if at_end and not counts:
        return ops + [TurningChain(n=n)]
    return [TurningChain(n=n, counts_as_stitch=counts)] + ops


def rectangle(rng: random.Random, pid: str) -> GenPattern:
    stitch = rng.choice(["sc", "sc", "hdc", "dc"])
    width = rng.randint(6, 30)
    tc = _turn_spec(rng, stitch)
    counts = tc[1] and stitch != "sc"
    at_end = (not tc[1]) and rng.random() < 0.35
    title = f"{rng.choice(_ADJ)} {rng.choice(_NOUN_FLAT)}"
    found, row1 = _row_start(rng, stitch, width, counts, same_line_chain=rng.random() < 0.3)
    if at_end:
        row1.program.ops.append(TurningChain(n=tc[0]))
    body = [row1]
    rows_left = rng.randint(4, 20)
    while rows_left > 0:
        size = rng.randint(1, rows_left) if rng.random() < 0.6 else 1
        ops = _turned([WorkRest(stitch=stitch)], tc, at_end)
        body.append(_counted("row", ops, width, range_len=size))
        rows_left -= size
        if rng.random() < 0.15:
            body.append(_note(rng.choice(["Change to color B.", "Change to color A.", "Do not fasten off."])))
    if rng.random() < 0.1:
        body.insert(rng.randint(1, len(body) - 1), GenLine(LineProgram(kind=LineKind.UNSUPPORTED, stated_count=width, unsupported_reason="chain spaces (lace)"), meta={"lace": "row"}))
    body += _maybe(rng, 0.7, rng.choice(["Fasten off and weave in ends.", "FO. Block if desired.", "Do not turn. Work a border if you like (not covered here)."]))
    lines = _header(rng, title, "rows") + found + _apply_ranges(body, 1)
    return GenPattern(pid, "rectangle", title, "rows", lines)


def triangle(rng: random.Random, pid: str) -> GenPattern:
    """Grows from a few stitches with an increase at both ends of every (other) row."""
    width = rng.choice([3, 3, 4])
    title = f"{rng.choice(_ADJ)} {rng.choice(_NOUN_TRI)}"
    found, row1 = _row_start(rng, "sc", width, False, same_line_chain=rng.random() < 0.3)
    body = [row1]
    every_other = rng.random() < 0.4
    for _ in range(rng.randint(4, 12)):
        if every_other:
            body.append(_counted("row", [TurningChain(n=1), WorkRest(stitch="sc")], width))
        ops = [TurningChain(n=1), IntoOne(stitch="sc", k=2), WorkRest(stitch="sc", leave=1), IntoOne(stitch="sc", k=2)]
        width += 2
        body.append(_counted("row", ops, width))
        if len(body) > 18:
            break
    body += _maybe(rng, 0.7, "Fasten off and weave in ends.")
    lines = _header(rng, title, "rows") + found + _apply_ranges(body, 1)
    return GenPattern(pid, "triangle", title, "rows", lines)


def trapezoid(rng: random.Random, pid: str) -> GenPattern:
    """Starts wide and decreases at both ends."""
    width = rng.randint(14, 32)
    title = f"{rng.choice(_ADJ)} {rng.choice(_NOUN_TRI)}"
    found, row1 = _row_start(rng, "sc", width, False, same_line_chain=rng.random() < 0.3)
    body = [row1]
    every_other = rng.random() < 0.4
    while width >= 8 and len(body) < 18:
        if every_other:
            body.append(_counted("row", [TurningChain(n=1), WorkRest(stitch="sc")], width))
        ops = [TurningChain(n=1), Together(stitch="sc", k=2), WorkRest(stitch="sc", leave=2), Together(stitch="sc", k=2)]
        width -= 2
        body.append(_counted("row", ops, width))
    body += _maybe(rng, 0.7, "Fasten off and weave in ends.")
    lines = _header(rng, title, "rows") + found + _apply_ranges(body, 1)
    return GenPattern(pid, "trapezoid", title, "rows", lines)


def _mixed_ops(rng: random.Random, width: int) -> list:
    """Symmetric 'sc a, hdc b, dc c, hdc b, sc a' (or with tr in the middle)."""
    while True:  # width >= 10, so a = b = 1 always fits
        a, b = rng.randint(1, 4), rng.randint(1, 3)
        c = width - 2 * a - 2 * b
        if c >= 1:
            break
    mid = rng.choice(["dc", "dc", "tr"])
    return [Work(stitch="sc", n=a), Work(stitch="hdc", n=b), Work(stitch=mid, n=c), Work(stitch="hdc", n=b), Work(stitch="sc", n=a)]


def mixed(rng: random.Random, pid: str) -> GenPattern:
    """Flat rows alternating plain sc rows and mixed-stitch 'wave' rows."""
    width = rng.randint(10, 26)
    title = f"Wavy {rng.choice(_NOUN_FLAT)}"
    found, row1 = _row_start(rng, "sc", width, False, same_line_chain=rng.random() < 0.3)
    body = [row1]
    for _ in range(rng.randint(3, 9)):
        ops = _mixed_ops(rng, width)
        body.append(_counted("row", [TurningChain(n=1)] + ops, width))
        body.append(_counted("row", [TurningChain(n=1), WorkRest(stitch="sc")], width, range_len=rng.choice([1, 1, 2])))
    body += _maybe(rng, 0.7, "Fasten off and weave in ends.")
    lines = _header(rng, title, "rows") + found + _apply_ranges(body, 1)
    return GenPattern(pid, "mixed", title, "rows", lines)


def two_part(rng: random.Random, pid: str) -> GenPattern:
    """A small amigurumi with two pieces under headings, each starting with its own magic ring."""
    k = rng.choice([6, 6, 5])
    title = f"{rng.choice(_ADJ)} {rng.choice(['Bunny', 'Bear', 'Chick', 'Mouse', 'Frog'])}"
    head, count = _circle(rng, k, rng.randint(2, 4), False)
    head += _even_rounds(rng, count, rng.randint(1, 4))
    n = count // k - 1
    for j in range(n, max(n - 2, 0), -1):
        head.append(_counted("round", _dec_round(rng, k, j), k * j))
    ear_k = rng.choice([4, 5, 6])
    ear, ear_count = _circle(rng, ear_k, 1, False)
    ear += _even_rounds(rng, ear_count, rng.randint(1, 4))
    body = [_note(rng.choice(["HEAD", "Head (make 1)", "Body:"]))] + _apply_ranges(head, 1)
    body += [_note("FO, leave a tail."), _note(rng.choice(["EARS (make 2)", "Ears - make 2", "Arms (make 2):"]))] + _apply_ranges(ear, 1)
    body += _maybe(rng, 0.6, "FO and sew to the head.")
    lines = _header(rng, title, "spiral") + body
    return GenPattern(pid, "two_part", title, "spiral", lines)


GENERATORS = {
    "sphere": sphere,
    "cylinder": cylinder,
    "cone": cone,
    "rectangle": rectangle,
    "triangle": triangle,
    "trapezoid": trapezoid,
    "mixed": mixed,
    "two_part": two_part,
}


def generate(rng: random.Random, shape: str, pid: str, max_lines: int = 25, min_lines: int = 6) -> GenPattern:
    for _ in range(50):
        p = GENERATORS[shape](rng, pid)
        if min_lines <= len(p.lines) <= max_lines:
            return p
    raise RuntimeError(f"could not generate a {shape} within {min_lines}-{max_lines} lines")
