"""The counting engine.

Takes the stitch programs for a pattern, in order, and works out for every line how many
stitches are available, used and made, compares that with the stated count, and explains
the result with a deterministic template. No model is involved here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .schema import (
    IntoOne,
    LineKind,
    LineProgram,
    Op,
    Repeat,
    Skip,
    Together,
    TurningChain,
    Work,
    WorkRest,
)

COUNT_MISMATCH = "COUNT_MISMATCH"
OVERFLOW = "OVERFLOW"
LEFTOVER = "LEFTOVER"
REPEAT_REMAINDER = "REPEAT_REMAINDER"
NO_STATED_COUNT = "NO_STATED_COUNT"
CANT_CHECK = "CANT_CHECK"

ERROR_CODES = (COUNT_MISMATCH, OVERFLOW, LEFTOVER, REPEAT_REMAINDER)
WARNING_CODES = (NO_STATED_COUNT,)

MAX_REPEAT = 500  # guard against absurd "x5000" transcriptions


class Status(str, Enum):
    OK = "OK"
    ERROR = "ERROR"
    WARNING = "WARNING"
    CANT_CHECK = "CAN'T CHECK"
    NOTE = "NOTE"


# ---------------------------------------------------------------------------
# Plain-words description of a program
# ---------------------------------------------------------------------------


def describe_op(op: Op) -> str:
    if isinstance(op, Work):
        return f"{op.stitch} {op.n}"
    if isinstance(op, IntoOne):
        return "inc" if (op.k == 2 and op.stitch == "sc") else f"{op.k} {op.stitch} in next st"
    if isinstance(op, Together):
        if op.k == 2 and op.stitch == "sc":
            return "dec"
        return f"{op.stitch.replace(' ', '')}{op.k}tog"
    if isinstance(op, Skip):
        return f"skip {op.n}"
    if isinstance(op, WorkRest):
        if op.leave:
            return f"{op.stitch} across to last {op.leave} st" if op.leave > 1 else f"{op.stitch} across to last st"
        return f"{op.stitch} in each remaining st"
    if isinstance(op, TurningChain):
        return f"ch {op.n}" + (" (counts as st)" if op.counts_as_stitch else "")
    if isinstance(op, Repeat):
        inner = ", ".join(describe_op(o) for o in op.body)
        if len(op.body) > 1 or isinstance(op.body[0], Repeat):
            inner = f"({inner})"
        return f"{inner} x{op.times}" if op.times is not None else f"{inner} around"
    raise TypeError(op)


def describe_ops(ops: list[Op]) -> str:
    return ", ".join(describe_op(o) for o in ops) if ops else "(nothing)"


def describe_program(p: LineProgram) -> str:
    """Plain-words summary used in the results table."""
    if p.kind == LineKind.NOTE:
        return "note (not a row)"
    if p.kind == LineKind.UNSUPPORTED:
        return f"can't check: {p.unsupported_reason or 'unsupported'}"
    if p.kind == LineKind.FOUNDATION:
        n = _foundation_chains(p)
        return f"chain {n}" if n is not None else "foundation chain (count unknown)"
    bits = []
    if p.start.type == "magic_ring":
        bits.append("in a magic ring:")
    elif p.start.type == "chain":
        bits.append(f"ch {p.start.chain_count},")
    if p.start.skip_chains:
        s = f"skip {p.start.skip_chains} ch"
        if p.start.skipped_count_as_stitch:
            s += " (count as 1 st)"
        bits.append(s + ",")
    bits.append(describe_ops(p.ops))
    if not p.must_use_all:
        bits.append("(rest left unworked)")
    return " ".join(bits)


# ---------------------------------------------------------------------------
# Executing one row
# ---------------------------------------------------------------------------


class _CantCheck(Exception):
    pass


def _body_consumption(ops: list[Op]) -> int | None:
    """Stitches one pass of `ops` consumes, or None if it depends on what's left."""
    total = 0
    for op in ops:
        if isinstance(op, Work):
            total += op.n
        elif isinstance(op, IntoOne):
            total += 1
        elif isinstance(op, Together):
            total += op.k
        elif isinstance(op, Skip):
            total += op.n
        elif isinstance(op, TurningChain):
            total += 1 if op.counts_as_stitch else 0
        elif isinstance(op, Repeat):
            if op.times is None:
                return None
            inner = _body_consumption(op.body)
            if inner is None:
                return None
            total += inner * op.times
        elif isinstance(op, WorkRest):
            return None
    return total


@dataclass
class RowSim:
    available: int
    used: int = 0
    made: int = 0
    codes: list[str] = field(default_factory=list)
    remainder: tuple[str, int, int, int] | None = None  # (repeat text, per pass, stitches at start, left over)


class _Exec:
    def __init__(self, available: int, ring: bool):
        self.ring = ring
        self.remaining = available
        self.used = 0
        self.made = 0
        self.overflow = False
        self.remainder: tuple[str, int, int, int] | None = None

    def take(self, n: int) -> None:
        if self.ring:
            return
        if n > self.remaining:
            self.overflow = True
        self.remaining -= n
        self.used += n

    def run(self, ops: list[Op]) -> None:
        for i, op in enumerate(ops):
            if isinstance(op, WorkRest) or (isinstance(op, Repeat) and op.times is None):
                # "sc to end" / "rep from * around" stop early to leave room for what follows.
                tail = _body_consumption(ops[i + 1 :]) if i + 1 < len(ops) else 0
                if tail is None:
                    raise _CantCheck("can't tell where the repeat stops, because of what follows it")
                self.op(op, tail)
            else:
                self.op(op)

    def op(self, op: Op, tail: int = 0) -> None:
        if isinstance(op, Work):
            self.take(op.n)
            self.made += op.n
        elif isinstance(op, IntoOne):
            self.take(1)
            self.made += op.k
        elif isinstance(op, Together):
            self.take(op.k)
            self.made += 1
        elif isinstance(op, Skip):
            self.take(op.n)
        elif isinstance(op, TurningChain):
            if op.counts_as_stitch:
                # Worked in place of the first stitch: uses it and counts as one made.
                self.take(1)
                self.made += 1
        elif isinstance(op, WorkRest):
            if self.ring:
                raise _CantCheck("'in each stitch around' can't be worked into a magic ring")
            # "sc to last st" says how many to leave; plain "sc across" leaves room for what follows.
            n = max(self.remaining - (op.leave if op.leave else tail), 0)
            self.take(n)
            self.made += n
        elif isinstance(op, Repeat):
            if op.times is not None:
                if op.times > MAX_REPEAT:
                    raise _CantCheck(f"repeat count {op.times} is implausibly large")
                for _ in range(op.times):
                    self.run(op.body)
                return
            if self.ring:
                raise _CantCheck("a repeat 'around' in a magic ring has no stitches to count against")
            per = _body_consumption(op.body)
            if not per:
                raise _CantCheck("can't tell how many times this repeat is worked")
            start = self.remaining - tail
            if start < 0:
                return  # already overflowing; nothing sensible to add
            passes, left = divmod(start, per)
            for _ in range(passes):
                self.run(op.body)
            if left or passes == 0:
                self.remainder = (describe_op(Repeat(times=1, body=op.body)).removesuffix(" x1"), per, start, left)
        else:  # pragma: no cover
            raise TypeError(op)


def _start_base(p: LineProgram, prev: int | None) -> tuple[int, int, bool]:
    """Return (available, made_before_ops, ring) for one row of `p`."""
    st = p.start
    if st.type == "magic_ring":
        return 0, 0, True
    if st.type == "chain":
        if st.chain_count is None:
            raise _CantCheck("the starting chain count isn't given")
        base = st.chain_count
    else:
        if prev is None:
            raise _CantCheck("_prev_unknown")
        base = prev
    available = base - st.skip_chains
    if available < 0:
        raise _CantCheck(f"skips {st.skip_chains} chains but only {base} exist")
    return available, (1 if st.skipped_count_as_stitch else 0), False


def simulate_row(p: LineProgram, prev: int | None) -> RowSim:
    available, made0, ring = _start_base(p, prev)
    ex = _Exec(available, ring)
    ex.made = made0
    ex.run(p.ops)
    row = RowSim(available=available, used=ex.used, made=ex.made, remainder=ex.remainder)
    if ex.overflow:
        row.codes.append(OVERFLOW)
    if ex.remainder is not None:
        row.codes.append(REPEAT_REMAINDER)
    if (
        p.must_use_all
        and not ring
        and ex.remaining > 0
        and not ex.overflow
        and ex.remainder is None
    ):
        row.codes.append(LEFTOVER)
    if p.stated_count is not None and p.stated_count != row.made:
        row.codes.insert(0, COUNT_MISMATCH)
    return row


# ---------------------------------------------------------------------------
# Whole pattern
# ---------------------------------------------------------------------------


@dataclass
class LineResult:
    index: int
    label: str | None
    kind: str
    status: Status
    available: int | None = None
    used: int | None = None
    made: int | None = None
    stated: int | None = None
    codes: list[str] = field(default_factory=list)
    explanation: str = ""
    program_text: str = ""
    rows: list[RowSim] = field(default_factory=list)
    assumed_stated_from: str | None = None  # label of the row whose stated count we started from

    @property
    def is_error(self) -> bool:
        return self.status == Status.ERROR

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "label": self.label,
            "kind": self.kind,
            "status": self.status.value,
            "available": self.available,
            "used": self.used,
            "made": self.made,
            "stated": self.stated,
            "codes": list(self.codes),
            "explanation": self.explanation,
            "program_text": self.program_text,
        }


def _foundation_chains(p: LineProgram) -> int | None:
    if p.start.chain_count is not None:
        return p.start.chain_count
    if p.ops and all(isinstance(o, Work) and o.stitch in ("ch", "chain") for o in p.ops):
        return sum(o.n for o in p.ops)  # type: ignore[union-attr]
    return None


def _has_errors(row: RowSim) -> bool:
    return any(c in ERROR_CODES for c in row.codes)


def _quote(text: str) -> str:
    return f"'{text}'"


def _explain(name: str, p: LineProgram, row: RowSim, ring: bool) -> str:
    prog = _quote(describe_ops(p.ops))
    stated = p.stated_count
    if ring:
        work = f"{prog} worked into the magic ring makes {row.made}"
    elif OVERFLOW in row.codes:
        work = f"{prog} needs {row.used} stitches, but only {row.available} are available (it would make {row.made})"
    else:
        work = f"{prog} uses {row.used} of {row.available} stitches and makes {row.made}"
    others = [c for c in row.codes if c != COUNT_MISMATCH]
    if stated is None:
        text = f"{name}: {work}. The pattern doesn't state a count for this row."
    elif stated == row.made:
        text = f"{name} says ({stated}). {work}" + (", so this matches." if not others else ", which matches the stated count.")
    else:
        text = f"{name} says ({stated}), but {work}."
    if LEFTOVER in row.codes:
        text += f" The row is worked across or around, but {row.available - row.used} stitches are left unworked."
    if REPEAT_REMAINDER in row.codes and row.remainder:
        rep, per, start, left = row.remainder
        if start < per:
            text += f" The repeat '{rep}' needs {per} stitches each time but only {start} are left."
        else:
            text += (
                f" The repeat '{rep}' uses {per} stitches each time and is worked to the end, but {start} stitches "
                f"don't divide evenly by {per} ({left} left over)."
            )
    return text


def _row_word(p: LineProgram) -> str:
    return "round" if p.kind == LineKind.ROUND else "row"


def _simulate_counted_line(
    p: LineProgram, candidates: list[int | None], name: str
) -> tuple[list[RowSim], int | None, bool]:
    """Simulate every row of the line. Returns (rows, index of candidate used, ring).

    `candidates` are possible starting counts: the previous row's made count first, then
    its stated count. If the previous row was wrong, a later row that works from the
    designer's stated count is checked from that count, so one mistake doesn't cascade.
    """
    ring = p.start.type == "magic_ring"
    uses_prev = p.start.type == "continue"
    best: tuple[list[RowSim], int | None] | None = None
    for ci, cand in enumerate(candidates if uses_prev else [None]):
        rows: list[RowSim] = []
        prev = cand
        for _ in range(p.row_count):
            row = simulate_row(p, prev)
            rows.append(row)
            if row.codes and p.stated_count is not None and _has_errors(row):
                # Within a range, carry on from the stated count, as the designer intends.
                prev = p.stated_count if row.made != p.stated_count else row.made
            else:
                prev = row.made
        if best is None:
            best = (rows, ci if uses_prev else None)
        if not any(_has_errors(r) for r in rows):
            return rows, (ci if uses_prev else None), ring
    assert best is not None
    return best[0], best[1], ring


def simulate(programs: list[LineProgram | None]) -> list[LineResult]:
    results: list[LineResult] = []
    prev_made: int | None = None
    prev_stated: int | None = None
    prev_label: str | None = None
    unknown_reason: str | None = "there is no foundation chain or magic ring before it"

    for i, p in enumerate(programs):
        if p is None:
            results.append(
                LineResult(
                    index=i,
                    label=None,
                    kind="unreadable",
                    status=Status.CANT_CHECK,
                    codes=[CANT_CHECK],
                    explanation="StitchProof couldn't read this line, so it can't be checked.",
                    program_text="(unreadable)",
                )
            )
            prev_made, prev_stated = None, None
            unknown_reason = "an earlier line couldn't be read"
            continue

        name = p.label or "This row"
        res = LineResult(index=i, label=p.label, kind=p.kind.value, status=Status.OK, program_text=describe_program(p))

        if p.kind == LineKind.NOTE:
            res.status = Status.NOTE
            res.explanation = "Not a row; ignored for counting."
            results.append(res)
            continue

        if p.kind == LineKind.UNSUPPORTED:
            reason = p.unsupported_reason or "this construction is outside what v1 can count"
            res.status = Status.CANT_CHECK
            res.codes = [CANT_CHECK]
            res.stated = p.stated_count
            res.explanation = f"Can't check {name if p.label else 'this line'}: {reason}."
            if p.stated_count is not None:
                res.explanation += f" The next row is checked from its stated count of {p.stated_count}."
            results.append(res)
            prev_made, prev_stated, prev_label = p.stated_count, None, p.label
            unknown_reason = None if p.stated_count is not None else f"{name if p.label else 'an earlier line'} couldn't be checked"
            continue

        if p.kind == LineKind.FOUNDATION:
            n = _foundation_chains(p)
            res.stated = p.stated_count
            if n is None:
                res.status = Status.CANT_CHECK
                res.codes = [CANT_CHECK]
                res.explanation = "Can't check: the foundation chain count isn't clear."
                prev_made, prev_stated = p.stated_count, None
                unknown_reason = None if p.stated_count is not None else "the foundation chain count isn't clear"
            else:
                res.made = n
                if p.stated_count is not None and p.stated_count != n:
                    res.status = Status.ERROR
                    res.codes = [COUNT_MISMATCH]
                    res.explanation = f"{name} says ({p.stated_count}), but the chain is {n} long."
                else:
                    res.explanation = f"Foundation chain of {n}."
                prev_made, prev_stated = n, p.stated_count
                unknown_reason = None
            prev_label = p.label
            results.append(res)
            continue

        # Counted row or round.
        candidates: list[int | None] = []
        if prev_made is not None:
            candidates.append(prev_made)
        if prev_stated is not None and prev_stated != prev_made:
            candidates.append(prev_stated)
        if p.start.type == "continue" and not candidates:
            res.status = Status.CANT_CHECK
            res.codes = [CANT_CHECK]
            res.stated = p.stated_count
            res.explanation = f"Can't check {name}: the starting stitch count is unknown because {unknown_reason}."
            if p.stated_count is not None:
                res.explanation += f" Later rows are checked from its stated count of {p.stated_count}."
                prev_made, prev_stated, unknown_reason = p.stated_count, None, None
            else:
                unknown_reason = f"{name} couldn't be checked"
            prev_label = p.label
            results.append(res)
            continue

        try:
            rows, ci, ring = _simulate_counted_line(p, candidates, name)
        except _CantCheck as e:
            msg = str(e)
            res.status = Status.CANT_CHECK
            res.codes = [CANT_CHECK]
            res.stated = p.stated_count
            res.explanation = f"Can't check {name}: {msg}."
            results.append(res)
            prev_made, prev_stated, prev_label = p.stated_count, None, p.label
            unknown_reason = None if p.stated_count is not None else f"{name} couldn't be checked"
            continue

        if ci:
            res.assumed_stated_from = prev_label or "the previous row"

        # Pick the row to report: the first with an error, else the first row.
        bad = [k for k, r in enumerate(rows) if _has_errors(r)]
        k = bad[0] if bad else 0
        row = rows[k]
        res.rows = rows
        res.available, res.used, res.made, res.stated = row.available, row.used, row.made, p.stated_count
        codes: list[str] = []
        for r in rows:
            for c in r.codes:
                if c not in codes:
                    codes.append(c)
        if p.stated_count is None:
            codes.append(NO_STATED_COUNT)
        res.codes = codes

        shown = name
        if p.row_count > 1 and bad:
            shown = f"{name} ({_row_word(p)} {p.range_start + k} of the range)"  # type: ignore[operator]
        text = _explain(shown, p, row, ring)
        if p.row_count > 1 and not bad:
            text += f" The same holds for each {_row_word(p)} {p.range_start} to {p.range_end}."
        if ci:
            src = prev_label or "the previous row"
            text += f" (Checked from the {candidates[ci]} stitches stated for {src}, since that row's instructions don't match it.)"
        res.explanation = text
        res.status = Status.ERROR if any(c in ERROR_CODES for c in codes) else (Status.WARNING if codes else Status.OK)
        results.append(res)

        last = rows[-1]
        prev_made, prev_stated, prev_label = last.made, p.stated_count, p.label
        unknown_reason = None
    return results


# ---------------------------------------------------------------------------
# Maker mode: one row, a known previous count
# ---------------------------------------------------------------------------


def check_single_row(p: LineProgram, previous_count: int | None) -> tuple[str, LineResult]:
    """Answer 'is the pattern wrong, or am I?' for one row.

    Returns a one-sentence answer and the full line result.
    """
    programs: list[LineProgram | None] = []
    if p.start.type == "continue" and p.kind in (LineKind.ROW, LineKind.ROUND):
        if previous_count is None:
            res = simulate([p])[0]
            return "Enter how many stitches you had at the end of the previous row.", res
        programs.append(LineProgram(kind=LineKind.FOUNDATION, start={"type": "chain", "chain_count": previous_count}))
    programs.append(p)
    res = simulate(programs)[-1]
    res.index = 0
    if res.status in (Status.CANT_CHECK, Status.NOTE):
        return res.explanation, res
    said = f"The pattern says {res.stated}." if res.stated is not None else "The pattern doesn't say how many stitches you should have."
    if res.available is not None and p.start.type == "continue":
        made = f"These instructions make {res.made} from your {res.available} stitches."
    else:
        made = f"These instructions make {res.made}."
    verdict = ""
    if res.status == Status.ERROR:
        verdict = " The pattern itself doesn't add up here, so it's not you."
    elif res.status == Status.OK:
        verdict = " The pattern is right; if your count differs, recount this row."
    return f"{said} {made}{verdict}", res
