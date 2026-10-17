from stitchproof.eval.metrics import PatternPrediction, Rate, score
from stitchproof.eval.run_eval import map_flag, parse_direct
from stitchproof.generate.build_dataset import EVAL_MIX, make_pattern
from stitchproof.schema import LineProgram
from stitchproof.simulate import simulate


def _records(n=20):
    return [make_pattern("mtest", i, EVAL_MIX, heldout=True) for i in range(n)]


def _perfect(rec):
    progs = [LineProgram.model_validate(l["gold"]) for l in rec["lines"]]
    res = simulate(progs)
    return PatternPrediction(rec["id"], {r.index for r in res if r.status.value == "ERROR"}, [r.status.value for r in res], progs)


def test_rate_formatting():
    r = Rate(50, 60)
    assert str(r) == "83.3% (50/60)"
    assert str(Rate()) == "n/a (0/0)"


def test_perfect_parse_scores_perfectly():
    recs = _records()
    m = score(recs, {r["id"]: _perfect(r) for r in recs}, "parse")
    assert m.errors_caught.num == m.errors_caught.den > 0
    assert m.false_alarms.num == 0 and m.false_alarms.den > 0
    assert m.pattern_accuracy.num == m.pattern_accuracy.den
    assert m.line_exact.num == m.line_exact.den
    assert m.count_equiv.num == m.count_equiv.den
    assert m.stated_faithful.num == m.stated_faithful.den


def test_parse_failures_count_as_wrong():
    recs = _records(5)
    preds = {r["id"]: PatternPrediction(r["id"], set(), ["CAN'T CHECK"] * len(r["lines"]), [None] * len(r["lines"])) for r in recs}
    m = score(recs, preds, "parse")
    assert m.valid_json.num == 0 and m.line_exact.num == 0 and m.count_equiv.num == 0 and m.errors_caught.num == 0


def test_flag_everything_has_full_false_alarms():
    recs = _records(5)
    preds = {r["id"]: PatternPrediction(r["id"], set(range(len(r["lines"]))), valid=True) for r in recs}
    m = score(recs, preds, "direct")
    assert m.false_alarms.num == m.false_alarms.den
    assert m.flags_on_non_rows > 0


def test_parse_direct_and_map_flags():
    rec = make_pattern("mtest", 3, EVAL_MIX, heldout=True)
    counted = [i for i, l in enumerate(rec["lines"]) if l["gold"]["kind"] in ("row", "round")]
    target = counted[2]
    label = rec["lines"][target]["gold"]["label"]
    rows = parse_direct('Sure! ```{"errors":[{"row":"%s","reason":"x"}]}```' % label)
    assert rows == [label]
    assert map_flag(rec, rows[0], set()) == target
    assert parse_direct("everything looks fine") is None
    assert parse_direct('{"errors": []}') == []
