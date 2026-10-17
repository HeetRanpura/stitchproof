"""Seed known errors into a pattern's gold programs (the text is rendered from them afterwards).

The model is never trained to find errors, only to transcribe; detection comes from the
simulator. Each seeding is verified: after seeding, the simulator run on the gold programs
must flag exactly the expected lines with ERROR, otherwise the seeding is retried.
"""
from __future__ import annotations

import random
from dataclasses import asdict, dataclass

from ..schema import IntoOne, LineKind, Repeat, Work
from ..simulate import Status, simulate
from .shapes import GenPattern

ERROR_TYPES = ["WRONG_STATED", "WRONG_REPEAT_TIMES", "WRONG_RUN_LENGTH", "WRONG_FOUNDATION", "NON_DIVISIBLE_AROUND"]
WARNING_TYPES = ["MISSING_STATED"]


@dataclass
class SeededError:
    type: str
    line: int  # the line that should be flagged
    source_line: int  # the line whose text was changed
    detail: str

    def to_dict(self) -> dict:
        return asdict(self)


def _counted(p) -> bool:
    return p.kind in (LineKind.ROW, LineKind.ROUND)


def _gold_status(pattern: GenPattern) -> list:
    return simulate([gl.program for gl in pattern.lines])


def _available(pattern: GenPattern, i: int) -> int | None:
    return _gold_status(pattern)[i].available


def _next_counted(pattern: GenPattern, i: int) -> int | None:
    for j in range(i + 1, len(pattern.lines)):
        if _counted(pattern.lines[j].program):
            return j
        if pattern.lines[j].program.kind != LineKind.NOTE:
            return None
    return None


def _wrong_stated(pattern: GenPattern, rng: random.Random) -> SeededError | None:
    cands = [i for i, gl in enumerate(pattern.lines) if _counted(gl.program) and gl.program.stated_count is not None]
    if not cands:
        return None
    i = rng.choice(cands)
    p = pattern.lines[i].program
    old = p.stated_count
    delta = rng.choice([-1, 1]) * rng.randint(1, 6)
    if old + delta <= 0:
        delta = abs(delta)
    p.stated_count = old + delta
    return SeededError("WRONG_STATED", i, i, f"stated count {old} -> {p.stated_count}")


def _top_repeats(p, fixed: bool):
    return [o for o in p.ops if isinstance(o, Repeat) and ((o.times is not None) == fixed)]


def _wrong_repeat_times(pattern: GenPattern, rng: random.Random) -> SeededError | None:
    cands = [i for i, gl in enumerate(pattern.lines) if _counted(gl.program) and any(r.times and r.times >= 2 for r in _top_repeats(gl.program, True))]
    if not cands:
        return None
    i = rng.choice(cands)
    rep = rng.choice([r for r in _top_repeats(pattern.lines[i].program, True) if r.times >= 2])
    old = rep.times
    rep.times = old + rng.choice([-1, 1]) if old > 2 else old + 1
    return SeededError("WRONG_REPEAT_TIMES", i, i, f"repeat x{old} -> x{rep.times}")


def _works_in(ops) -> list[Work]:
    out = []
    for o in ops:
        if isinstance(o, Work):
            out.append(o)
        elif isinstance(o, Repeat) and o.times is not None:
            out.extend(_works_in(o.body))
    return out


def _wrong_run_length(pattern: GenPattern, rng: random.Random) -> SeededError | None:
    cands = [i for i, gl in enumerate(pattern.lines) if _counted(gl.program) and gl.program.start.type != "magic_ring" and _works_in(gl.program.ops)]
    if not cands:
        return None
    i = rng.choice(cands)
    w = rng.choice(_works_in(pattern.lines[i].program.ops))
    old = w.n
    w.n = old + rng.choice([-1, 1]) if old > 1 else old + 1
    return SeededError("WRONG_RUN_LENGTH", i, i, f"{w.stitch} {old} -> {w.stitch} {w.n}")


def _wrong_foundation(pattern: GenPattern, rng: random.Random) -> SeededError | None:
    for i, gl in enumerate(pattern.lines):
        p = gl.program
        if p.kind == LineKind.FOUNDATION and p.start.chain_count:
            j = _next_counted(pattern, i)
            if j is None:
                return None
            target = j
        elif _counted(p) and p.start.type == "chain" and p.start.chain_count:
            target = i
        else:
            continue
        old = p.start.chain_count
        p.start.chain_count = max(2, old + rng.choice([-1, 1]) * rng.randint(1, 3))
        if p.start.chain_count == old:
            p.start.chain_count = old + 1
        return SeededError("WRONG_FOUNDATION", target, i, f"ch {old} -> ch {p.start.chain_count}")
    return None


def _non_divisible_around(pattern: GenPattern, rng: random.Random) -> SeededError | None:
    res = _gold_status(pattern)
    cands = []
    for i, gl in enumerate(pattern.lines):
        p = gl.program
        if not _counted(p) or res[i].available is None:
            continue
        for rep in _top_repeats(p, False):
            for w in rep.body:
                if isinstance(w, Work):
                    cands.append((i, rep, w))
            if all(isinstance(b, IntoOne) for b in rep.body):
                cands.append((i, rep, None))
    rng.shuffle(cands)
    for i, rep, w in cands:
        avail = res[i].available
        per = sum(b.n if isinstance(b, Work) else 1 for b in rep.body)
        if w is None:
            new_per = per + 1
            if avail % new_per:
                rep.body.insert(0, Work(stitch="sc", n=1))
                return SeededError("NON_DIVISIBLE_AROUND", i, i, f"'around' repeat now uses {new_per} sts per pass on {avail}")
            continue
        for delta in rng.sample([-1, 1], 2):
            if w.n + delta >= 1 and avail % (per + delta):
                old = w.n
                w.n += delta
                return SeededError("NON_DIVISIBLE_AROUND", i, i, f"'around' repeat {w.stitch} {old} -> {w.n} on {avail} sts")
    return None


SEEDERS = {
    "WRONG_STATED": _wrong_stated,
    "WRONG_REPEAT_TIMES": _wrong_repeat_times,
    "WRONG_RUN_LENGTH": _wrong_run_length,
    "WRONG_FOUNDATION": _wrong_foundation,
    "NON_DIVISIBLE_AROUND": _non_divisible_around,
}


def drop_stated_counts(pattern: GenPattern, rng: random.Random, p_line: float = 0.06) -> list[SeededError]:
    """MISSING_STATED: remove some stated counts (warning only)."""
    out = []
    for i, gl in enumerate(pattern.lines):
        if _counted(gl.program) and gl.program.stated_count is not None and rng.random() < p_line:
            out.append(SeededError("MISSING_STATED", i, i, f"stated count {gl.program.stated_count} removed"))
            gl.program.stated_count = None
    return out


def error_lines(pattern: GenPattern) -> set[int]:
    return {r.index for r in _gold_status(pattern) if r.status == Status.ERROR}


def seed(pattern: GenPattern, rng: random.Random, n_errors: int, tries: int = 30) -> tuple[GenPattern, list[SeededError]] | None:
    """Return a copy of `pattern` with n_errors verified errors, or None if it can't be done."""
    if error_lines(pattern):
        raise ValueError(f"{pattern.pid}: gold pattern is not clean before seeding")
    if n_errors == 0:
        return pattern.copy(), []
    for _ in range(tries):
        cand = pattern.copy()
        seeded: list[SeededError] = []
        types = rng.sample(ERROR_TYPES, len(ERROR_TYPES))
        for t in types:
            if len(seeded) == n_errors:
                break
            used = {s.line for s in seeded} | {s.source_line for s in seeded}
            trial = cand.copy()
            e = SEEDERS[t](trial, rng)
            if e is None or e.line in used or e.source_line in used:
                continue
            # Keep errors apart so each one is detectable on its own.
            if any(abs(e.line - s.line) < 2 for s in seeded):
                continue
            cand = trial
            seeded.append(e)
        if len(seeded) != n_errors:
            continue
        if error_lines(cand) == {s.line for s in seeded}:
            return cand, seeded
    return None
