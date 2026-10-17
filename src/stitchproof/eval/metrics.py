"""Evaluation metrics. Every rate is reported together with its count.

Definitions (lines are the segmented lines of a pattern):
- error line: a line the simulator flags with ERROR when run on the gold programs.
- clean row: a gold row/round/foundation line that is not an error line.
- errors caught: error lines the approach flags with ERROR / all error lines.
- false alarms: clean rows the approach flags with ERROR / all clean rows.
- flags on non-rows: ERROR flags on gold note/unsupported lines (reported as a count).
- pattern accuracy: patterns whose flagged-line set equals the error-line set exactly.
Parse failures count as wrong: an unreadable line is never a correct parse, a correct
count or a caught error. A direct-check answer that isn't valid JSON flags nothing and
its pattern counts as wrong at pattern level.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..canonical import programs_equal
from ..schema import LineKind, LineProgram
from ..simulate import Status, _CantCheck, simulate_row

COUNTED = ("row", "round", "foundation")


@dataclass
class Rate:
    num: int = 0
    den: int = 0

    def add(self, hit: bool) -> None:
        self.den += 1
        self.num += int(bool(hit))

    @property
    def value(self) -> float | None:
        return self.num / self.den if self.den else None

    def __str__(self) -> str:
        if not self.den:
            return "n/a (0/0)"
        return f"{100 * self.num / self.den:.1f}% ({self.num}/{self.den})"

    def to_dict(self) -> dict:
        return {"num": self.num, "den": self.den, "pct": None if not self.den else round(100 * self.num / self.den, 1)}


@dataclass
class PatternPrediction:
    """What an approach said about one pattern."""

    pattern_id: str
    flagged: set[int]  # line indices flagged ERROR
    statuses: list[str] | None = None  # per-line status (parse mode)
    programs: list[LineProgram | None] | None = None  # parse mode
    valid: bool = True  # direct mode: was the answer valid JSON


@dataclass
class Metrics:
    errors_caught: Rate = field(default_factory=Rate)
    false_alarms: Rate = field(default_factory=Rate)
    pattern_accuracy: Rate = field(default_factory=Rate)
    flags_on_non_rows: int = 0
    valid_json: Rate = field(default_factory=Rate)
    line_exact: Rate = field(default_factory=Rate)
    count_equiv: Rate = field(default_factory=Rate)
    stated_faithful: Rate = field(default_factory=Rate)
    cant_check_correct: int = 0
    cant_check_wrong: int = 0
    by_error_type: dict[str, Rate] = field(default_factory=dict)
    missing_stated_warned: Rate = field(default_factory=Rate)

    def to_dict(self) -> dict:
        out = {}
        for k, v in self.__dict__.items():
            if isinstance(v, Rate):
                out[k] = v.to_dict()
            elif isinstance(v, dict):
                out[k] = {kk: vv.to_dict() for kk, vv in sorted(v.items())}
            else:
                out[k] = v
        return out


def _gold_programs(record: dict) -> list[LineProgram]:
    return [LineProgram.model_validate(l["gold"]) for l in record["lines"]]


def _count_equivalent(pred: LineProgram, gold: LineProgram, gold_avail: int | None, gold_used: int | None, gold_made: int | None) -> bool:
    if pred.kind.value not in COUNTED:
        return False
    if gold.kind == LineKind.FOUNDATION:
        from ..canonical import canonical

        return pred.kind == LineKind.FOUNDATION and canonical(pred)["start"]["chain_count"] == canonical(gold)["start"]["chain_count"]
    if gold_made is None or gold_avail is None:
        return False
    # The previous row's count, before this row's own chain skips.
    prev = gold_avail + gold.start.skip_chains if gold.start.type == "continue" else None
    try:
        row = simulate_row(pred, prev)
    except _CantCheck:
        return False
    return (row.used, row.made) == (gold_used, gold_made) and pred.row_count == gold.row_count


def score(records: list[dict], preds: dict[str, PatternPrediction], mode: str) -> Metrics:
    from ..simulate import simulate

    m = Metrics()
    for rec in records:
        pred = preds.get(rec["id"])
        gold = _gold_programs(rec)
        truth_err = set(rec["error_lines"])
        flagged = pred.flagged if pred else set()
        for i, line in enumerate(rec["lines"]):
            kind = line["gold"]["kind"]
            if i in truth_err:
                m.errors_caught.add(i in flagged)
            elif kind in COUNTED:
                m.false_alarms.add(i in flagged)
            elif i in flagged:
                m.flags_on_non_rows += 1
        m.pattern_accuracy.add(pred is not None and pred.valid and flagged == truth_err)

        line_to_error = {e["line"]: e["type"] for e in rec["seeded_errors"]}
        for i, t in line_to_error.items():
            m.by_error_type.setdefault(t, Rate()).add(i in flagged)
        for e in rec.get("missing_stated", []):
            if pred and pred.statuses:
                m.missing_stated_warned.add(pred.statuses[e["line"]] in (Status.WARNING.value, Status.ERROR.value))

        if mode == "direct":
            m.valid_json.add(pred is not None and pred.valid)
            continue

        gold_res = simulate(gold)
        progs = pred.programs if pred and pred.programs else [None] * len(gold)
        statuses = pred.statuses if pred and pred.statuses else [Status.CANT_CHECK.value] * len(gold)
        for i, (g, p) in enumerate(zip(gold, progs)):
            m.valid_json.add(p is not None)
            m.line_exact.add(programs_equal(p, g))
            gr = gold_res[i]
            if g.kind.value in COUNTED and gr.made is not None:
                m.count_equiv.add(p is not None and _count_equivalent(p, g, gr.available, gr.used, gr.made))
                m.stated_faithful.add(p is not None and p.stated_count == g.stated_count)
            if statuses[i] == Status.CANT_CHECK.value and p is not None and p.kind == LineKind.UNSUPPORTED:
                if g.kind == LineKind.UNSUPPORTED:
                    m.cant_check_correct += 1
                else:
                    m.cant_check_wrong += 1
    return m
