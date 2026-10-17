"""Template renderer: gold programs -> pattern text, in many notation styles.

A Style fixes one option per slot for a whole pattern (designers are mostly consistent),
and each line has a small chance of switching to another allowed option. Four options are
held out of training and used only in eval_synth (HELDOUT below).
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, fields, replace

from ..schema import IntoOne, LineKind, LineProgram, Repeat, Skip, Together, TurningChain, Work, WorkRest
from ..segment import segment
from .shapes import GenLine, GenPattern

NUM_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"]
ORD = {1: "2nd", 2: "3rd", 3: "4th", 4: "5th"}
FULL = {"sc": "single crochet", "hdc": "half double crochet", "dc": "double crochet", "tr": "treble crochet"}

OPTIONS: dict[str, list[str]] = {
    "label": ["rnd", "r", "num_paren", "round", "upper", "r_dot", "dash"],
    "rep_fixed": ["x", "x_sp", "star_n", "bracket", "stars_times", "times", "repeat_word", "nx", "more_times"],
    "rep_around": ["around", "bracket_around", "rep_star", "stars_around", "rep_paren"],
    "run": ["s_n", "n_s", "next", "ns", "each_of_next"],
    "inc": ["inc", "2_in_next", "2_in_same", "increase", "sc_inc"],
    "dec": ["dec", "sc2tog", "invdec", "inv_dec", "decrease", "sc_dec"],
    "rest": ["plain", "each", "one_each", "to_end"],
    "stated": ["paren", "bracket", "paren_sts", "paren_name", "dash_st", "dash_sts", "stitches", "should_have"],
    "mr": ["in_mr", "mr_comma", "magic_ring", "ring_then", "ch2", "adjustable"],
    "found": ["ch_dot", "ch", "chain", "foundation", "loosely"],
    "row1": ["from_hook", "from_hook2", "starting", "each_remaining"],
    "turn": ["ch_turn", "ch_and_turn", "turn_ch", "ch_turn_dot"],
}

HELDOUT: dict[str, str] = {
    "label": "dash",  # "Round 3 -" / "Row 3 -"
    "rep_fixed": "more_times",  # "*sc, inc; rep from * 5 more times"
    "stated": "should_have",  # "You should have 18 sts."
    "run": "each_of_next",  # "sc in each of the next 3 st"
}


@dataclass(frozen=True)
class Style:
    label: str
    rep_fixed: str
    rep_around: str
    run: str
    inc: str
    dec: str
    rest: str
    stated: str
    mr: str
    found: str
    row1: str
    turn: str
    caps: bool = False
    full_words: bool = False
    period: bool = False
    switch_p: float = 0.12


def allowed(slot: str, heldout: bool) -> list[str]:
    opts = OPTIONS[slot]
    if heldout:
        return opts
    return [o for o in opts if HELDOUT.get(slot) != o]


def sample_style(rng: random.Random, heldout: bool = False) -> Style:
    """Training styles never use held-out options; eval styles always use all four."""
    kw = {}
    for slot in OPTIONS:
        if heldout and slot in HELDOUT:
            kw[slot] = HELDOUT[slot]
        else:
            kw[slot] = rng.choice(allowed(slot, False))
    return Style(
        **kw,
        caps=rng.random() < 0.1,
        full_words=rng.random() < 0.08,
        period=rng.random() < 0.3,
    )


def uses_heldout(style: Style) -> bool:
    return any(getattr(style, k) == v for k, v in HELDOUT.items())


class _LineRenderer:
    def __init__(self, style: Style, rng: random.Random, heldout: bool):
        self.base = style
        self.rng = rng
        self.heldout = heldout
        self.s = style

    def begin_line(self) -> None:
        """Per-line variety: occasionally switch one non-held-out slot."""
        self.s = self.base
        if self.rng.random() < self.base.switch_p:
            slot = self.rng.choice([f.name for f in fields(Style) if f.name in OPTIONS and f.name not in HELDOUT])
            self.s = replace(self.base, **{slot: self.rng.choice(allowed(slot, False))})

    # -- pieces ----------------------------------------------------------------
    def name(self, stitch: str) -> str:
        if self.s.full_words and stitch in FULL and self.rng.random() < 0.5:
            return FULL[stitch]
        return stitch

    def run(self, stitch: str, n: int) -> str:
        s = self.name(stitch)
        st = self.s.run
        if n == 1:
            return {"s_n": s, "n_s": f"1 {s}", "next": f"{s} in next st", "ns": f"1{s}" if s == stitch else f"1 {s}", "each_of_next": f"{s} in the next st"}[st]
        return {
            "s_n": f"{s} {n}",
            "n_s": f"{n} {s}",
            "next": f"{s} in next {n} sts",
            "ns": f"{n}{s}" if s == stitch else f"{n} {s}",
            "each_of_next": f"{s} in each of the next {n} st",
        }[st]

    def inc(self, stitch: str, k: int) -> str:
        if stitch == "sc" and k == 2:
            return {"inc": "inc", "2_in_next": "2 sc in next st", "2_in_same": "2 sc in same st", "increase": "increase", "sc_inc": "sc inc"}[self.s.inc]
        s = self.name(stitch)
        if k == 2 and self.s.inc in ("inc", "sc_inc"):
            return f"{s} inc"
        return f"{k} {s} in {'same' if self.s.inc == '2_in_same' else 'next'} st"

    def dec(self, stitch: str, k: int) -> str:
        if stitch == "sc" and k == 2:
            return {"dec": "dec", "sc2tog": "sc2tog", "invdec": "invdec", "inv_dec": "inv dec", "decrease": "decrease", "sc_dec": "sc dec"}[self.s.dec]
        return f"{stitch}{k}tog"

    def rest(self, stitch: str, leave: int, kind: str, blo: bool = False) -> str:
        s = self.name(stitch) + (" " + self.rng.choice(["in BLO", "in back loops only", "blo"]) if blo else "")
        if leave:
            last = "last st" if leave == 1 else f"last {leave} sts"
            return {
                "plain": f"{s} across to {last}",
                "each": f"{s} in each st to {last}",
                "one_each": f"1 {s} in each st to {last}",
                "to_end": f"{s} to {last}",
            }[self.s.rest]
        where = "around" if kind == "round" else "across"
        return {
            "plain": f"{s} {where}",
            "each": f"{s} in each st {where}",
            "one_each": f"1 {s} in each st {where}",
            "to_end": f"{s} to end" if kind == "row" else f"{s} in each st around",
        }[self.s.rest]

    def repeat(self, op: Repeat, kind: str) -> str:
        body = self.ops(op.body, kind)
        single = len(op.body) == 1
        if op.times is None:
            # "inc around" / "2 sc in each st around"
            if single and isinstance(op.body[0], IntoOne) and self.rng.random() < 0.5:
                b = op.body[0]
                return f"{b.k} {self.name(b.stitch)} in each st {'around' if kind == 'round' else 'across'}"
            where = "around" if kind == "round" else self.rng.choice(["across", "to end"])
            st = self.s.rep_around
            p = body if single else f"({body})"
            return {
                "around": f"{p} {where}",
                "bracket_around": f"[{body}] {where}",
                "rep_star": f"*{body}; rep from * {where}",
                "stars_around": f"*{body}* {where}",
                "rep_paren": f"rep {p} {where}",
            }[st]
        n = op.times
        nw = NUM_WORDS[n] if n < len(NUM_WORDS) else str(n)
        st = self.s.rep_fixed
        if st == "more_times":
            more = n - 1
            return f"*{body}; rep from * {more} more time{'s' if more != 1 else ''}"
        p = body if single else f"({body})"
        return {
            "x": f"{p} x{n}",
            "x_sp": f"{p} x {n}",
            "star_n": f"{p} * {n}",
            "bracket": f"[{body}] x{n}",
            "stars_times": f"*{body}* {n} times",
            "times": f"{p} {n} times",
            "repeat_word": f"repeat {p} {nw} times",
            "nx": f"[{body}] {n}x",
        }[st]

    def op(self, op, kind: str) -> str:
        if isinstance(op, Work):
            return self.run(op.stitch, op.n)
        if isinstance(op, IntoOne):
            return self.inc(op.stitch, op.k)
        if isinstance(op, Together):
            return self.dec(op.stitch, op.k)
        if isinstance(op, Skip):
            return f"sk {op.n}" if op.n > 1 else "sk next st"
        if isinstance(op, WorkRest):
            return self.rest(op.stitch, op.leave, kind, blo=self.rng.random() < 0.06)
        if isinstance(op, Repeat):
            return self.repeat(op, kind)
        raise TypeError(op)

    def ops(self, ops, kind: str) -> str:
        return ", ".join(self.op(o, kind) for o in ops)

    def turning(self, tc: TurningChain, kind: str, stitch: str) -> str:
        if kind == "round":
            return f"ch {tc.n}"
        if tc.counts_as_stitch:
            return self.rng.choice(
                [
                    f"ch {tc.n} (counts as {stitch}), turn",
                    f"ch {tc.n} (counts as first {stitch}), turn",
                    f"turn, ch {tc.n} (counts as a st)",
                    f"ch {tc.n} (counts as 1 {stitch} throughout), turn",
                ]
            )
        extra = " (does not count as a st)" if tc.n >= 2 and self.rng.random() < 0.5 else ""
        return {
            "ch_turn": f"ch {tc.n}{extra}, turn",
            "ch_and_turn": f"ch {tc.n}{extra} and turn",
            "turn_ch": f"turn, ch {tc.n}{extra}",
            "ch_turn_dot": f"ch{tc.n}{extra}, turn",
        }[self.s.turn]

    def stated(self, n: int, stitch: str) -> str:
        return {
            "paren": f" ({n})",
            "bracket": f" [{n}]",
            "paren_sts": f" ({n} sts)",
            "paren_name": f" ({n} {stitch})",
            "dash_st": f" - {n} st",
            "dash_sts": f" - {n} sts",
            "stitches": f" - {n} stitches",
            "should_have": self.rng.choice([f". You should have {n} sts", f". You should have {n} stitches", f" (you should have {n})"]),
        }[self.s.stated]

    def label(self, kind: str, p: LineProgram, row_no: int) -> tuple[str, str]:
        """Return (prefix as written, gold label)."""
        a, b = (p.range_start, p.range_end) if p.range_start is not None else (row_no, None)
        R = "Rnd" if kind == "round" else "Row"
        W = "Round" if kind == "round" else "Row"
        st = self.s.label
        if b is None:
            prefix = {
                "rnd": f"{R} {a}:",
                "r": f"R{a}:",
                "num_paren": f"{a})",
                "round": f"{W} {a}:",
                "upper": f"{R.upper()} {a}:",
                "r_dot": f"R{a}.",
                "dash": f"{W} {a} -",
            }[st]
        else:
            prefix = {
                "rnd": self.rng.choice([f"{R} {a}-{b}:", f"{R}s {a}-{b}:"]),
                "r": self.rng.choice([f"R{a}-{b}:", f"R{a}-R{b}:"]),
                "num_paren": f"{a}-{b})",
                "round": self.rng.choice([f"{W}s {a}-{b}:", f"{W}s {a} to {b}:"]),
                "upper": f"{R.upper()}S {a}-{b}:",
                "r_dot": f"R{a}-{b}.",
                "dash": f"{W}s {a}-{b} -",
            }[st]
        return prefix, prefix.rstrip(":.-) ").strip()


def _main_stitch(p: LineProgram) -> str:
    for op in p.ops:
        if isinstance(op, (Work, IntoOne, Together, WorkRest)):
            return op.stitch
        if isinstance(op, Repeat):
            return _main_stitch(LineProgram(kind="row", ops=op.body))
    return "sc"


def _stitch_names(ops) -> set[str]:
    out: set[str] = set()
    for op in ops:
        if isinstance(op, Repeat):
            out |= _stitch_names(op.body)
        elif hasattr(op, "stitch"):
            out.add(op.stitch)
    return out


def _single_stitch(p: LineProgram) -> bool:
    return len(_stitch_names(p.ops)) <= 1


def _caps(text: str) -> str:
    return re.sub(r"\b(sc|hdc|dc|tr|inc|dec|ch|blo|sk|mr|invdec|sc2tog)\b", lambda m: m.group(1).upper(), text)


def _render_counted(lr: _LineRenderer, gl: GenLine, p: LineProgram) -> str:
    kind = p.kind.value if p.kind in (LineKind.ROW, LineKind.ROUND) else "round"
    row_no = gl.meta.get("row_no", 1)
    prefix, gold_label = lr.label(kind, p, row_no)
    p.label = gold_label
    stitch = _main_stitch(p)
    ops = list(p.ops)
    pieces: list[str] = []

    if p.start.type == "magic_ring":
        n = ops[0].n  # type: ignore[union-attr]
        s = lr.name("sc")
        pieces.append(
            {
                "in_mr": f"{n} {s} in MR",
                "mr_comma": f"MR, {n} {s}",
                "magic_ring": f"{n} {s} in magic ring",
                "ring_then": f"magic ring, {n} {s} in ring",
                "ch2": f"ch 2, {n} {s} in 2nd ch from hook",
                "adjustable": f"{n} {s} into an adjustable ring",
            }[lr.s.mr]
        )
        ops = ops[1:]
    elif p.start.skip_chains:
        o = ORD[p.start.skip_chains]
        counts = ""
        if p.start.skipped_count_as_stitch:
            counts = lr.rng.choice([f" (skipped ch count as {stitch})", f" (skipped chains count as first {stitch})", f" (the skipped ch count as 1 {stitch})"])
        s = lr.name(stitch)
        chain_prefix = ""
        if p.start.type == "chain":
            chain_prefix = lr.rng.choice([f"ch {p.start.chain_count}, ", f"chain {p.start.chain_count}, then "])
        text = {
            "from_hook": f"{s} in {o} ch from hook{counts} and in each ch across",
            "from_hook2": f"{s} in {o} ch from hook{counts}, {s} in each ch across",
            "starting": f"starting in {o} ch from hook{counts}, {s} across",
            "each_remaining": f"{s} in {o} ch from hook{counts} and each remaining ch",
        }[lr.s.row1]
        pieces.append(chain_prefix + text)
        assert isinstance(ops[0], WorkRest)
        ops = ops[1:]

    lead_tc = ops[0] if ops and isinstance(ops[0], TurningChain) else None
    if lead_tc is not None:
        ops = ops[1:]
    tail_tc = ops[-1] if ops and isinstance(ops[-1], TurningChain) else None
    if tail_tc is not None:
        ops = ops[:-1]
    if lead_tc is not None:
        pieces.insert(0, lr.turning(lead_tc, kind, stitch))
        if lead_tc.counts_as_stitch and ops and isinstance(ops[0], WorkRest):
            s = lr.name(stitch)
            pieces.append(lr.rng.choice([f"{s} in next st and in each st across", f"skip first st, {s} in each st across", f"{s} in each st across"]))
            ops = ops[1:]
    if ops:
        pieces.append(lr.ops(ops, kind))
    if tail_tc is not None:
        pieces.append(lr.turning(tail_tc, "row", stitch))
    body = ", ".join(pieces)
    if gl.meta.get("joined"):
        body += lr.rng.choice([", join with sl st to first sc", ", join with a sl st", ", sl st to join", ", join"])
    if lr.s.caps:
        body = _caps(body)
    body = body[:1].upper() + body[1:]
    stated = lr.stated(p.stated_count, stitch if _single_stitch(p) else "sts") if p.stated_count is not None else ""
    end = "." if lr.s.period else ""
    return f"{prefix} {body}{stated}{end}"


def _render_unsupported(lr: _LineRenderer, gl: GenLine, p: LineProgram) -> str:
    kind = "round" if gl.meta.get("lace") in ("open", "close") else "row"
    prefix, gold_label = lr.label(kind, p, gl.meta.get("row_no", 1))
    p.label = gold_label
    n = p.stated_count
    lace = gl.meta.get("lace")
    if lace == "open":
        body = lr.rng.choice(["(sc, ch 1, sk next st) around", "*sc in next st, ch 1, sk 1; rep from * around"])
    elif lace == "close":
        body = lr.rng.choice(["sc in each sc and ch-sp around", "sc in each st and in each ch-1 sp around"])
    else:
        body = lr.rng.choice(["ch 1, turn, (sc, ch 1, sk next st) across", "ch 1, turn, *sc, ch 1, sk 1; rep from * across"])
    stated = lr.stated(n, "sts") if n is not None else ""
    return f"{prefix} {body[:1].upper() + body[1:]}{stated}"


def _render_foundation(lr: _LineRenderer, p: LineProgram) -> str:
    n = p.start.chain_count
    return {
        "ch_dot": f"Ch {n}.",
        "ch": f"Ch {n}",
        "chain": f"Chain {n}.",
        "foundation": f"Foundation: ch {n}",
        "loosely": f"Ch {n} loosely.",
    }[lr.s.found]


@dataclass
class Rendered:
    texts: list[str]
    programs: list[LineProgram]

    @property
    def text(self) -> str:
        return "\n".join(self.texts)


def render(pattern: GenPattern, style: Style, rng: random.Random, heldout: bool = False) -> Rendered:
    lr = _LineRenderer(style, rng, heldout)
    texts: list[str] = []
    programs: list[LineProgram] = []
    for gl in pattern.lines:
        p = gl.program.model_copy(deep=True)
        lr.begin_line()
        if gl.text is not None:
            texts.append(gl.text)
        elif p.kind == LineKind.FOUNDATION:
            texts.append(_render_foundation(lr, p))
        elif p.kind == LineKind.UNSUPPORTED:
            texts.append(_render_unsupported(lr, gl, p))
        else:
            texts.append(_render_counted(lr, gl, p))
        programs.append(p)
    seg = segment("\n".join(texts))
    if len(seg.lines) != len(texts):
        raise ValueError("rendered pattern does not segment back into the same lines")
    return Rendered([l.text for l in seg.lines], programs)
