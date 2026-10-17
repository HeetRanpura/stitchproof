"""Pydantic models for the stitch program: the model's only output format."""
from __future__ import annotations

import json
from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


class LineKind(str, Enum):
    ROW = "row"  # flat row worked back and forth
    ROUND = "round"  # worked in the round
    FOUNDATION = "foundation"  # "Ch 21" on its own line
    NOTE = "note"  # ignored by the simulator
    UNSUPPORTED = "unsupported"


class Start(BaseModel):
    type: Literal["continue", "magic_ring", "chain"] = "continue"
    chain_count: int | None = None  # for type == "chain", e.g. "Ch 11. Row 1: ..." or a foundation line
    skip_chains: int = Field(default=0, ge=0)  # "sc in 2nd ch from hook" -> 1
    skipped_count_as_stitch: bool = False


class Work(BaseModel):
    """N stitches, one into each of the next N stitches."""

    t: Literal["work"] = "work"
    stitch: str  # "sc", "hdc", "dc", "tr", "sl st", "bobble", ...
    n: int = Field(ge=1)


class IntoOne(BaseModel):
    """Increase: k stitches into one stitch."""

    t: Literal["into_one"] = "into_one"
    stitch: str
    k: int = Field(ge=2)


class Together(BaseModel):
    """Decrease: k stitches worked together into one."""

    t: Literal["together"] = "together"
    stitch: str
    k: int = Field(ge=2)


class Skip(BaseModel):
    t: Literal["skip"] = "skip"
    n: int = Field(ge=1)


class WorkRest(BaseModel):
    """'sc in each st around/across', 'sc to end'; 'sc across to last st' has leave=1."""

    t: Literal["work_rest"] = "work_rest"
    stitch: str
    leave: int = Field(default=0, ge=0)  # stitches left for the ops that follow


class TurningChain(BaseModel):
    t: Literal["turning_chain"] = "turning_chain"
    n: int = Field(ge=1)
    counts_as_stitch: bool = False


class Repeat(BaseModel):
    t: Literal["repeat"] = "repeat"
    times: int | None = Field(default=None, ge=1)  # None: "around"/"to end", repeat until stitches run out
    body: list["Op"] = Field(min_length=1)


Op = Annotated[
    Union[Work, IntoOne, Together, Skip, WorkRest, TurningChain, Repeat],
    Field(discriminator="t"),
]
Repeat.model_rebuild()


class LineProgram(BaseModel):
    kind: LineKind
    label: str | None = None  # "Rnd 3", "Row 12", "R5"
    range_start: int | None = None  # "Rnd 5-10" -> 5
    range_end: int | None = None  # -> 10
    start: Start = Field(default_factory=Start)
    ops: list[Op] = Field(default_factory=list)
    must_use_all: bool = True  # False if text says leave stitches unworked
    stated_count: int | None = None  # exactly as written, even if wrong
    unsupported_reason: str | None = None

    @property
    def row_count(self) -> int:
        """How many rows this line stands for (a range "Rnd 5-10" is 6)."""
        if self.range_start is not None and self.range_end is not None and self.range_end > self.range_start:
            return self.range_end - self.range_start + 1
        return 1


def _compact(obj):
    """Drop fields equal to their default, but always keep the op tag 't'."""
    if isinstance(obj, BaseModel):
        out = {}
        for name, field in type(obj).model_fields.items():
            value = getattr(obj, name)
            if name == "t":
                out[name] = value
                continue
            default = field.get_default(call_default_factory=True)
            if value == default:
                continue
            out[name] = _compact(value)
        return out
    if isinstance(obj, list):
        return [_compact(v) for v in obj]
    if isinstance(obj, Enum):
        return obj.value
    return obj


def to_compact_dict(program: LineProgram) -> dict:
    d = _compact(program)
    d["kind"] = program.kind.value  # kind has no default but keep it first for readability
    return {"kind": d.pop("kind"), **d}


def to_compact_json(program: LineProgram) -> str:
    """The canonical training-target serialisation: compact, defaults omitted."""
    return json.dumps(to_compact_dict(program), separators=(",", ":"), ensure_ascii=False)
