"""Canonicalise programs so that equivalent transcriptions compare equal.

Rules: stitch names are normalised; adjacent runs of the same stitch merge; a repeat of 1
is unwrapped; a fixed repeat of a single run becomes one run ("(sc) x6" == "sc 6");
foundation chains are stored as start.chain_count; row and round are treated alike (they
count the same); labels and free-text reasons are ignored; a one-row range is no range.
Notes and unsupported lines compare by kind only.
"""
from __future__ import annotations

import json

from .schema import LineKind, LineProgram, Repeat, Work

STITCH_SYNONYMS = {
    "single crochet": "sc",
    "single": "sc",
    "invdec": "sc",
    "inv dec": "sc",
    "invisible decrease": "sc",
    "half double crochet": "hdc",
    "half double": "hdc",
    "double crochet": "dc",
    "double": "dc",
    "treble crochet": "tr",
    "treble": "tr",
    "triple": "tr",
    "trc": "tr",
    "slip stitch": "sl st",
    "slst": "sl st",
    "sl sts": "sl st",
    "slip stitches": "sl st",
    "ss": "sl st",
    "chain": "ch",
    "puff stitch": "puff",
    "bobble stitch": "bobble",
    "popcorn stitch": "popcorn",
}


def norm_stitch(s: str) -> str:
    s = " ".join(s.lower().replace("_", " ").replace("-", " ").split())
    if s in STITCH_SYNONYMS:
        return STITCH_SYNONYMS[s]
    if s.endswith("s") and s[:-1] in ("sc", "hdc", "dc", "tr", "sl st"):
        return s[:-1]
    return s


def _canon_ops(ops: list) -> list[dict]:
    out: list[dict] = []
    for op in ops:
        d = op.model_dump()
        if "stitch" in d:
            d["stitch"] = norm_stitch(d["stitch"])
        if isinstance(op, Repeat):
            body = _canon_ops(op.body)
            if op.times == 1:
                out.extend(body)
                continue
            if op.times is not None and len(body) == 1 and body[0]["t"] == "work":
                d = {"t": "work", "stitch": body[0]["stitch"], "n": body[0]["n"] * op.times}
            else:
                d["body"] = body
        if (
            d["t"] == "work"
            and out
            and out[-1]["t"] == "work"
            and out[-1]["stitch"] == d["stitch"]
        ):
            out[-1] = {**out[-1], "n": out[-1]["n"] + d["n"]}
            continue
        out.append(d)
    return out


def canonical(p: LineProgram) -> dict:
    if p.kind in (LineKind.NOTE, LineKind.UNSUPPORTED):
        return {"kind": p.kind.value}
    start = p.start.model_dump()
    ops = p.ops
    if p.kind == LineKind.FOUNDATION:
        if start["chain_count"] is None and ops and all(isinstance(o, Work) for o in ops):
            start["chain_count"] = sum(o.n for o in ops)  # type: ignore[union-attr]
            ops = []
        start["type"] = "chain"
    rs, re_ = p.range_start, p.range_end
    if rs is not None and (re_ is None or re_ == rs):
        rs = re_ = None
    return {
        "kind": "counted" if p.kind in (LineKind.ROW, LineKind.ROUND) else p.kind.value,
        "range": [rs, re_],
        "start": start,
        "ops": _canon_ops(ops),
        "must_use_all": p.must_use_all,
        "stated_count": p.stated_count,
    }


def canonical_key(p: LineProgram) -> str:
    return json.dumps(canonical(p), sort_keys=True)


def programs_equal(a: LineProgram | None, b: LineProgram | None) -> bool:
    if a is None or b is None:
        return False
    return canonical_key(a) == canonical_key(b)
