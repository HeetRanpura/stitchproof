"""Simulator golden tests, one test per error code, and one test per counting convention.

Convention tests are named test_rule_<N>_... after CONVENTIONS.md.
"""
import pytest

from helpers import chain, dec, inc, mr, note, rep, rest, rnd, row, sc, skip, turn, unsupported
from stitchproof.schema import Start
from stitchproof.simulate import (
    CANT_CHECK,
    COUNT_MISMATCH,
    LEFTOVER,
    NO_STATED_COUNT,
    OVERFLOW,
    REPEAT_REMAINDER,
    Status,
    check_single_row,
    describe_program,
    simulate,
)


def statuses(results):
    return [r.status for r in results]


def made(results):
    return [r.made for r in results]


# ---------------------------------------------------------------------------
# Golden patterns
# ---------------------------------------------------------------------------


def sphere():
    lines = [mr("Rnd 1", 6, stated=6), rnd("Rnd 2", rep(6, inc()), stated=12)]
    for i in range(3, 7):
        lines.append(rnd(f"Rnd {i}", rep(6, sc(i - 2), inc()), stated=6 * i))
    lines.append(rnd("Rnd 7-12", rest(), stated=36, rng=(7, 12)))
    for j, n in enumerate([30, 24, 18, 12]):
        lines.append(rnd(f"Rnd {13 + j}", rep(6, sc(n // 6 - 1), dec()), stated=n))
    lines.append(rnd("Rnd 17", rep(6, dec()), stated=6))
    return lines


def test_golden_sphere():
    res = simulate(sphere())
    assert all(s == Status.OK for s in statuses(res)), [r.explanation for r in res]
    assert made(res) == [6, 12, 18, 24, 30, 36, 36, 30, 24, 18, 12, 6]
    assert len(res[6].rows) == 6 and all(r.made == 36 for r in res[6].rows)
    assert res[3].explanation == "Rnd 4 says (24). '(sc 2, inc) x6' uses 18 of 18 stitches and makes 24, so this matches."


def test_golden_sc_rectangle_from_ch_11():
    lines = [
        chain(11, label="Ch 11"),
        row("Row 1", rest(), stated=10, start=Start(skip_chains=1)),
        row("Row 2-10", turn(1), rest(), stated=10, rng=(2, 10)),
    ]
    res = simulate(lines)
    assert statuses(res) == [Status.OK] * 3
    assert made(res) == [11, 10, 10]
    assert res[1].available == 10


def test_golden_sc_rectangle_chain_on_same_line():
    res = simulate([row("Row 1", rest(), stated=10, start=Start(type="chain", chain_count=11, skip_chains=1))])
    assert res[0].status == Status.OK and res[0].made == 10


def test_golden_dc_rectangle_ch3_counts_as_dc():
    lines = [
        chain(13),
        row("Row 1", rest("dc"), stated=11, start=Start(skip_chains=3, skipped_count_as_stitch=True)),
        row("Row 2", turn(3, counts=True), rest("dc"), stated=11),
        row("Row 3-8", turn(3, counts=True), rest("dc"), stated=11, rng=(3, 8)),
    ]
    res = simulate(lines)
    assert statuses(res) == [Status.OK] * 4, [r.explanation for r in res]
    assert made(res) == [13, 11, 11, 11]


def test_golden_triangle_increases_at_both_ends():
    lines = [chain(3), row("Row 1", rest(), stated=2, start=Start(skip_chains=1))]
    for i in range(2, 8):
        lines.append(row(f"Row {i}", turn(1), inc(), rest(leave=1), inc(), stated=2 * i))
    res = simulate(lines)
    assert all(s == Status.OK for s in statuses(res)), [r.explanation for r in res]
    assert made(res)[1:] == [2, 4, 6, 8, 10, 12, 14]


def test_golden_mixed_stitch_row():
    lines = [chain(15), row("Row 1", sc(3), sc(2, "hdc"), sc(2, "dc"), sc(2, "tr"), sc(2, "dc"), sc(2, "hdc"), sc(1), stated=14, start=Start(skip_chains=1))]
    res = simulate(lines)
    assert res[1].status == Status.OK and res[1].made == 14


# ---------------------------------------------------------------------------
# One test per error / warning code
# ---------------------------------------------------------------------------


def test_code_count_mismatch():
    res = simulate([mr("Rnd 1", 6, 6), rnd("Rnd 2", rep(6, inc()), stated=12), rnd("Rnd 3", rep(6, sc(), inc()), stated=19)])
    assert res[2].status == Status.ERROR and res[2].codes == [COUNT_MISMATCH]
    assert res[2].explanation == "Rnd 3 says (19), but '(sc 1, inc) x6' uses 12 of 12 stitches and makes 18."


def test_code_overflow():
    s = sphere()[:4] + [rnd("Rnd 5", rep(6, sc(4), inc()), stated=36)]
    res = simulate(s)
    assert res[4].status == Status.ERROR
    assert OVERFLOW in res[4].codes
    assert "needs 30 stitches, but only 24 are available" in res[4].explanation


def test_code_leftover():
    s = sphere()[:3] + [rnd("Rnd 4", rep(5, sc(2), inc()), stated=20)]
    res = simulate(s)
    assert res[3].codes == [LEFTOVER]
    assert "3 stitches are left unworked" in res[3].explanation


def test_code_repeat_remainder():
    s = sphere()[:3] + [rnd("Rnd 4", rep(None, sc(3), inc()), stated=22)]
    res = simulate(s)
    assert REPEAT_REMAINDER in res[3].codes
    assert "18 stitches don't divide evenly by 4 (2 left over)" in res[3].explanation


def test_code_no_stated_count_is_warning_only():
    res = simulate([mr("Rnd 1", 6, 6), rnd("Rnd 2", rep(6, inc()))])
    assert res[1].status == Status.WARNING and res[1].codes == [NO_STATED_COUNT]
    assert "doesn't state a count" in res[1].explanation


def test_code_cant_check_unsupported_and_unknown_count():
    res = simulate([mr("Rnd 1", 6, 6), unsupported("chain spaces (lace)", label="Rnd 2"), rnd("Rnd 3", rest(), stated=6)])
    assert res[1].status == Status.CANT_CHECK and res[1].codes == [CANT_CHECK]
    assert "chain spaces" in res[1].explanation
    assert res[2].status == Status.CANT_CHECK and "unknown" in res[2].explanation


# ---------------------------------------------------------------------------
# One test per counting convention (CONVENTIONS.md)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("stitch", ["sc", "hdc", "dc", "tr", "sl st", "bobble", "popcorn", "puff", "cluster"])
def test_rule_1_one_in_one(stitch):
    res = simulate([chain(7), row("Row 1", rest(stitch), stated=6, start=Start(skip_chains=1)), row("Row 2", turn(), sc(6, stitch), stated=6)])
    assert res[2].status == Status.OK and res[2].used == 6 and res[2].made == 6


def test_rule_2_increases_any_stitch():
    res = simulate([mr("Rnd 1", 6, 6), rnd("Rnd 2", rep(6, inc(3)), stated=18), rnd("Rnd 3", rep(6, sc(2, "dc"), inc(2, "dc")), stated=24)])
    assert statuses(res) == [Status.OK] * 3
    assert (res[1].used, res[1].made) == (6, 18)


def test_rule_3_decreases():
    res = simulate([chain(13), row("Row 1", rest(), stated=12, start=Start(skip_chains=1)), row("Row 2", turn(), rep(4, dec(3)), stated=4), row("Row 3", turn(), rep(2, dec(2, "dc")), stated=2)])
    assert statuses(res) == [Status.OK] * 4
    assert (res[2].used, res[2].made) == (12, 4)


def test_rule_4_loop_modifiers_dont_change_counts():
    # "sc in BLO around" is transcribed as plain sc around: the loop is not part of the program.
    plain = simulate([mr("Rnd 1", 6, 6), rnd("Rnd 2", rest(), stated=6)])
    assert plain[1].status == Status.OK and plain[1].made == 6


def test_rule_5_magic_ring_uses_nothing():
    res = simulate([mr("Rnd 1", 6, stated=6)])
    assert (res[0].available, res[0].used, res[0].made) == (0, 0, 6)
    res = simulate([rnd("Rnd 1", rep(None, inc()), stated=12, start=Start(type="magic_ring"))])
    assert res[0].status == Status.CANT_CHECK


@pytest.mark.parametrize("skip_n,stitch", [(1, "sc"), (2, "hdc"), (3, "dc")])
def test_rule_6_skipped_chains_dont_count(skip_n, stitch):
    res = simulate([chain(20), row("Row 1", rest(stitch), stated=20 - skip_n, start=Start(skip_chains=skip_n))])
    assert res[1].status == Status.OK


def test_rule_6_skipped_chains_count_when_text_says_so():
    res = simulate([chain(20), row("Row 1", rest("dc"), stated=18, start=Start(skip_chains=3, skipped_count_as_stitch=True))])
    assert res[1].status == Status.OK and res[1].made == 18


def test_rule_7_turning_chain_not_counted_by_default():
    res = simulate([chain(11), row("Row 1", rest(), stated=10, start=Start(skip_chains=1)), row("Row 2", turn(2), rest("hdc"), stated=10)])
    assert res[2].status == Status.OK and res[2].made == 10


def test_rule_7_counting_turning_chain_uses_first_stitch():
    res = simulate([chain(13), row("Row 1", rest("dc"), stated=11, start=Start(skip_chains=3, skipped_count_as_stitch=True)), row("Row 2", turn(3, counts=True), sc(10, "dc"), stated=11)])
    assert res[2].status == Status.OK and (res[2].used, res[2].made) == (11, 11)


def test_rule_8_joined_round_chain_and_join_dont_count():
    # "Ch 1, sc around, join with sl st": the ch 1 is a non-counting chain, the join isn't transcribed.
    res = simulate([mr("Rnd 1", 6, 6), rnd("Rnd 2", turn(1), rep(6, inc()), stated=12)])
    assert res[1].status == Status.OK


def test_rule_9_around_must_use_all_but_leave_unworked_is_ok():
    res = simulate([chain(11), row("Row 1", rest(), stated=10, start=Start(skip_chains=1)), row("Row 2", turn(), sc(8), stated=8, must_use_all=False)])
    assert res[2].status == Status.OK
    res = simulate([chain(11), row("Row 1", rest(), stated=10, start=Start(skip_chains=1)), row("Row 2", turn(), sc(8), stated=8)])
    assert res[2].codes == [LEFTOVER]


def test_rule_10_repeat_around_and_fixed_repeat_agree():
    fixed = simulate(sphere()[:3] + [rnd("Rnd 4", rep(6, sc(2), inc()), stated=24)])
    around = simulate(sphere()[:3] + [rnd("Rnd 4", rep(None, sc(2), inc()), stated=24)])
    assert fixed[3].status == around[3].status == Status.OK
    assert fixed[3].made == around[3].made == 24


def test_rule_10_repeat_to_last_stitches():
    # "*sc 2, inc; rep from * to last 2 st, sc 2" on 17 stitches: 5 repeats + 2 = 17 used, 22 made.
    res = simulate([chain(18), row("Row 1", rest(), stated=17, start=Start(skip_chains=1)), row("Row 2", turn(), rep(None, sc(2), inc()), sc(2), stated=22)])
    assert res[2].status == Status.OK, res[2].explanation


def test_rule_10_nested_repeats():
    res = simulate(sphere()[:2] + [rnd("Rnd 3", rep(3, rep(2, sc(), inc())), stated=18)])
    assert res[2].status == Status.OK


def test_rule_11_range_applies_stated_count_to_each_row():
    res = simulate(sphere()[:6] + [rnd("Rnd 7-9", rep(6, sc(5), inc()), stated=42, rng=(7, 9))])
    r = res[6]
    assert r.status == Status.ERROR
    assert [x.made for x in r.rows][0] == 42
    assert "Rnd 7-9 (round 8 of the range)" in r.explanation


def test_rule_12_stated_count_compared_and_missing_is_warning():
    res = simulate([mr("Rnd 1", 6), mr("Rnd 1", 6, stated=7)])
    assert res[0].status == Status.WARNING and res[1].status == Status.ERROR


def test_rule_13_notes_ignored_between_rows():
    res = simulate([mr("Rnd 1", 6, 6), note(), note(), rnd("Rnd 2", rep(6, inc()), stated=12)])
    assert statuses(res) == [Status.OK, Status.NOTE, Status.NOTE, Status.OK]


def test_rule_14_out_of_scope_is_cant_check_with_reason():
    res = simulate([unsupported("multi-size pattern")])
    assert res[0].status == Status.CANT_CHECK and "multi-size" in res[0].explanation


def test_rule_15_one_wrong_stated_count_does_not_cascade():
    s = sphere()
    s[2] = rnd("Rnd 3", rep(6, sc(), inc()), stated=19)  # wrong stated count only
    res = simulate(s)
    assert [r.status for r in res].count(Status.ERROR) == 1 and res[2].status == Status.ERROR


def test_rule_15_wrong_repeat_count_resyncs_to_stated():
    s = sphere()
    s[2] = rnd("Rnd 3", rep(5, sc(), inc()), stated=18)  # "x5" typo: makes 15 + leftover
    res = simulate(s)
    assert res[2].status == Status.ERROR
    assert all(r.status == Status.OK for k, r in enumerate(res) if k != 2)
    assert "stated for Rnd 3" in res[3].explanation


def test_rule_15_cant_check_resumes_from_stated_count():
    res = simulate([mr("Rnd 1", 6, 6), unsupported("chain spaces", stated=12, label="Rnd 2"), rnd("Rnd 3", rep(6, sc(), inc()), stated=18)])
    assert res[2].status == Status.OK


def test_row_before_any_start_is_cant_check():
    res = simulate([rnd("Rnd 5", rest(), stated=24)])
    assert res[0].status == Status.CANT_CHECK


def test_unreadable_line_is_cant_check():
    res = simulate([mr("Rnd 1", 6, 6), None, rnd("Rnd 3", rest(), stated=6)])
    assert res[1].status == Status.CANT_CHECK and res[2].status == Status.CANT_CHECK


def test_skip_op_consumes_without_making():
    res = simulate([chain(11), row("Row 1", rest(), stated=10, start=Start(skip_chains=1)), row("Row 2", turn(), skip(1), sc(9), stated=9)])
    assert res[2].status == Status.OK


def test_foundation_stated_mismatch():
    res = simulate([chain(20, stated=21)])
    assert res[0].status == Status.ERROR


# ---------------------------------------------------------------------------
# Maker mode and descriptions
# ---------------------------------------------------------------------------


def test_maker_mode_pattern_wrong():
    answer, res = check_single_row(rnd("Rnd 5", rep(6, sc(3), inc()), stated=31), 24)
    assert answer.startswith("The pattern says 31. These instructions make 30 from your 24 stitches.")
    assert "not you" in answer


def test_maker_mode_pattern_right():
    answer, res = check_single_row(rnd("Rnd 5", rep(6, sc(3), inc()), stated=30), 24)
    assert "pattern is right" in answer and res.status == Status.OK


def test_describe_program():
    p = rnd("Rnd 4", rep(6, sc(2), inc()), stated=24)
    assert describe_program(p) == "(sc 2, inc) x6"
    assert describe_program(mr("Rnd 1", 6)) == "in a magic ring: sc 6"
