import pytest

from stitchproof.parse_output import parse_model_output
from stitchproof.schema import IntoOne, LineKind, Repeat, Skip, Work, WorkRest

GOOD = '{"kind":"round","label":"Rnd 3","ops":[{"t":"repeat","times":6,"body":[{"t":"work","stitch":"sc","n":1},{"t":"into_one","stitch":"sc","k":2}]}],"stated_count":18}'


def test_plain_json():
    r = parse_model_output(GOOD)
    assert r.ok and r.program.stated_count == 18 and isinstance(r.program.ops[0], Repeat)


def test_fenced_json():
    r = parse_model_output(f"Here you go:\n```json\n{GOOD}\n```\nHope that helps!")
    assert r.ok and r.program.label == "Rnd 3"


def test_trailing_and_leading_text():
    r = parse_model_output(f"Sure. {GOOD} Note: this round increases by 6.")
    assert r.ok


def test_think_block_removed():
    r = parse_model_output('<think>The count {"kind":"note"} hmm</think>\n' + GOOD)
    assert r.ok and r.program.kind == LineKind.ROUND


def test_unclosed_think_prefix():
    r = parse_model_output("reasoning... </think>" + GOOD)
    assert r.ok


@pytest.mark.parametrize("kind,expected", [("Rnd", LineKind.ROUND), ("ROW", LineKind.ROW), ("comment", LineKind.NOTE), ("foundation chain", LineKind.FOUNDATION)])
def test_kind_synonyms(kind, expected):
    r = parse_model_output('{"kind":"%s"}' % kind)
    assert r.ok and r.program.kind == expected


def test_missing_fields_get_defaults():
    r = parse_model_output('{"kind":"round"}')
    assert r.ok and r.program.ops == [] and r.program.start.type == "continue" and r.program.must_use_all


def test_null_fields_tolerated():
    r = parse_model_output('{"kind":"round","start":null,"ops":null,"stated_count":"18 sts"}')
    assert r.ok and r.program.stated_count == 18


def test_op_synonyms_and_inferred_tags():
    raw = '{"kind":"round","ops":[{"type":"inc","stitch":"sc","k":2},{"stitch":"sc","n":"3"},{"stitch":"sc"},{"n":1}],"stated_count":5}'
    r = parse_model_output(raw)
    assert r.ok, r.error
    ops = r.program.ops
    assert isinstance(ops[0], IntoOne) and isinstance(ops[1], Work) and ops[1].n == 3
    assert isinstance(ops[2], WorkRest) and isinstance(ops[3], Skip)


def test_start_as_string():
    r = parse_model_output('{"kind":"round","start":"magic ring","ops":[{"t":"work","stitch":"sc","n":6}]}')
    assert r.ok and r.program.start.type == "magic_ring"


def test_repeat_around_as_string():
    r = parse_model_output('{"kind":"round","ops":[{"t":"repeat","times":"around","body":[{"t":"into_one","stitch":"sc","k":2}]}]}')
    assert r.ok and r.program.ops[0].times is None


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "I can't parse this row.",
        '{"kind": "round", "ops": [',  # truncated
        '{"kind":"round","ops":[{"t":"work","stitch":"sc","n":0}]}',  # invalid n
        '{"kind":"teleport"}',
        "[1, 2, 3]",
    ],
)
def test_failures_return_none(raw):
    r = parse_model_output(raw)
    assert not r.ok and r.error


def test_first_valid_object_wins_over_inner_ops():
    # When the outer object is broken, an inner op dict must not be mistaken for a program.
    r = parse_model_output('{"kind":"round","ops":[{"t":"work","stitch":"sc","n":1}')
    assert not r.ok
