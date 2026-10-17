"""Robust extraction of a LineProgram from raw model text. Shared by eval and the app."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from .schema import LineProgram

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_FENCE_RE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.DOTALL)

_KIND_SYNONYMS = {
    "row": "row",
    "rows": "row",
    "round": "round",
    "rounds": "round",
    "rnd": "round",
    "rnds": "round",
    "foundation": "foundation",
    "foundation_chain": "foundation",
    "chain": "foundation",
    "note": "note",
    "notes": "note",
    "comment": "note",
    "instruction": "note",
    "unsupported": "unsupported",
    "unknown": "unsupported",
    "cant_check": "unsupported",
}

_OP_SYNONYMS = {
    "work": "work",
    "stitch": "work",
    "sts": "work",
    "into_one": "into_one",
    "intoone": "into_one",
    "inc": "into_one",
    "increase": "into_one",
    "together": "together",
    "dec": "together",
    "decrease": "together",
    "skip": "skip",
    "sk": "skip",
    "work_rest": "work_rest",
    "workrest": "work_rest",
    "rest": "work_rest",
    "turning_chain": "turning_chain",
    "turn": "turning_chain",
    "turning": "turning_chain",
    "repeat": "repeat",
    "rep": "repeat",
}

_START_SYNONYMS = {
    "continue": "continue",
    "magic_ring": "magic_ring",
    "magic ring": "magic_ring",
    "mr": "magic_ring",
    "magic_circle": "magic_ring",
    "adjustable_ring": "magic_ring",
    "chain": "chain",
    "ch": "chain",
    "foundation": "chain",
}


@dataclass
class ParseResult:
    program: LineProgram | None
    error: str | None
    raw: str

    @property
    def ok(self) -> bool:
        return self.program is not None


def _to_int(v: Any) -> Any:
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, str):
        m = re.search(r"-?\d+", v)
        if m:
            return int(m.group())
        if v.strip().lower() in ("", "none", "null", "around", "to end", "across"):
            return None
    return v


def _norm_op(op: Any) -> Any:
    if not isinstance(op, dict):
        return op
    op = dict(op)
    t = op.get("t", op.get("type", op.get("op")))
    op.pop("type", None)
    op.pop("op", None)
    if isinstance(t, str):
        t = _OP_SYNONYMS.get(t.strip().lower().replace(" ", "_"), t)
    if t is None:  # infer from keys
        if "body" in op:
            t = "repeat"
        elif "stitch" in op and "n" in op:
            t = "work"
        elif "stitch" in op and len(op) == 1:
            t = "work_rest"
        elif "n" in op and "counts_as_stitch" in op:
            t = "turning_chain"
        elif set(op) == {"n"}:
            t = "skip"
    if t is not None:
        op["t"] = t
    for key in ("n", "k", "times"):
        if key in op:
            op[key] = _to_int(op[key])
    if "stitch" in op and isinstance(op["stitch"], str):
        op["stitch"] = op["stitch"].strip()
    if isinstance(op.get("body"), list):
        op["body"] = [_norm_op(b) for b in op["body"]]
    elif isinstance(op.get("body"), dict):
        op["body"] = [_norm_op(op["body"])]
    return op


def normalise_dict(d: dict) -> dict:
    d = dict(d)
    kind = d.get("kind")
    if isinstance(kind, str):
        d["kind"] = _KIND_SYNONYMS.get(kind.strip().lower().replace(" ", "_"), kind.strip().lower())
    start = d.get("start")
    if isinstance(start, str):
        d["start"] = {"type": _START_SYNONYMS.get(start.strip().lower(), start)}
    elif isinstance(start, dict):
        start = dict(start)
        if isinstance(start.get("type"), str):
            start["type"] = _START_SYNONYMS.get(start["type"].strip().lower(), start["type"])
        for key in ("chain_count", "skip_chains"):
            if key in start:
                start[key] = _to_int(start[key])
        if start.get("skip_chains") is None:
            start.pop("skip_chains", None)
        d["start"] = start
    elif start is None:
        d.pop("start", None)
    for key in ("stated_count", "range_start", "range_end"):
        if key in d:
            d[key] = _to_int(d[key])
    if d.get("ops") is None:
        d.pop("ops", None)
    elif isinstance(d.get("ops"), list):
        d["ops"] = [_norm_op(o) for o in d["ops"]]
    if d.get("label") is not None and not isinstance(d["label"], str):
        d["label"] = str(d["label"])
    return d


def _candidate_objects(text: str):
    """Yield dicts found in text: fenced blocks first, then any top-level {...}."""
    decoder = json.JSONDecoder()
    sources = [m.group(1) for m in _FENCE_RE.finditer(text)] + [text]
    for src in sources:
        i = src.find("{")
        while i != -1:
            try:
                obj, _ = decoder.raw_decode(src, i)
                if isinstance(obj, dict):
                    yield obj
            except json.JSONDecodeError:
                pass
            i = src.find("{", i + 1)


def strip_thinking(text: str) -> str:
    text = _THINK_RE.sub("", text)
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    return text


def parse_model_output(text: str) -> ParseResult:
    cleaned = strip_thinking(text or "")
    last_error = "no JSON object found"
    for obj in _candidate_objects(cleaned):
        if "kind" not in obj and "ops" not in obj:
            continue  # probably a nested op; the outer object failed to decode
        try:
            return ParseResult(LineProgram.model_validate(normalise_dict(obj)), None, text)
        except (ValidationError, TypeError, ValueError) as e:
            last_error = f"schema: {str(e).splitlines()[0]}"
    return ParseResult(None, last_error, text)
