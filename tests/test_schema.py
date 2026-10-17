import json

import pytest
from pydantic import ValidationError

from helpers import inc, mr, rep, rnd, sc
from stitchproof.canonical import canonical, norm_stitch, programs_equal
from stitchproof.schema import LineProgram, Repeat, Start, Work, WorkRest, to_compact_json


def test_compact_json_omits_defaults_and_roundtrips():
    p = rnd("Rnd 3", rep(6, sc(), inc()), stated=18)
    s = to_compact_json(p)
    d = json.loads(s)
    assert list(d)[0] == "kind"
    assert "start" not in d and "must_use_all" not in d and "unsupported_reason" not in d
    assert d["ops"][0]["t"] == "repeat" and d["ops"][0]["times"] == 6
    assert LineProgram.model_validate_json(s) == p


def test_compact_json_keeps_non_default_start():
    s = to_compact_json(mr("Rnd 1", 6, 6))
    assert json.loads(s)["start"] == {"type": "magic_ring"}


def test_discriminator_picks_op_type():
    p = LineProgram.model_validate({"kind": "round", "ops": [{"t": "work_rest", "stitch": "sc"}]})
    assert isinstance(p.ops[0], WorkRest)


@pytest.mark.parametrize(
    "bad",
    [
        {"kind": "round", "ops": [{"t": "work", "stitch": "sc", "n": 0}]},
        {"kind": "round", "ops": [{"t": "into_one", "stitch": "sc", "k": 1}]},
        {"kind": "round", "ops": [{"t": "repeat", "times": 6, "body": []}]},
        {"kind": "round", "ops": [{"t": "teleport"}]},
        {"kind": "spiral"},
        {"ops": []},
    ],
)
def test_invalid_programs_rejected(bad):
    with pytest.raises(ValidationError):
        LineProgram.model_validate(bad)


def test_row_count():
    assert rnd("Rnd 5-10", rng=(5, 10)).row_count == 6
    assert rnd("Rnd 5").row_count == 1


# canonical.py


def test_canonical_equivalences():
    a = rnd("Rnd 7", sc(6))
    b = rnd("R7", rep(6, sc(1)))
    c = rnd("Round 7", sc(2), sc(4), kind="row")
    assert programs_equal(a, b) and programs_equal(a, c)


def test_canonical_stitch_names():
    assert norm_stitch("Single Crochet") == "sc"
    assert norm_stitch("slip stitch") == "sl st"
    assert norm_stitch("dcs") == "dc"
    assert norm_stitch("invdec") == "sc"
    a = rnd("Rnd 1", Work(stitch="single crochet", n=3))
    assert programs_equal(a, rnd("Rnd 1", sc(3)))


def test_canonical_differences_matter():
    assert not programs_equal(rnd("Rnd 3", rep(6, sc(), inc()), stated=18), rnd("Rnd 3", rep(6, sc(), inc()), stated=19))
    assert not programs_equal(rnd("Rnd 3", rep(6, sc(), inc())), rnd("Rnd 3", rep(None, sc(), inc())))
    assert not programs_equal(None, rnd("Rnd 3"))


def test_canonical_foundation_forms_agree():
    a = LineProgram(kind="foundation", start=Start(type="chain", chain_count=21))
    b = LineProgram(kind="foundation", ops=[Work(stitch="ch", n=21)])
    assert canonical(a) == canonical(b)


def test_canonical_notes_compare_by_kind():
    assert programs_equal(LineProgram(kind="note", label="x"), LineProgram(kind="note"))
    assert programs_equal(
        LineProgram(kind="unsupported", unsupported_reason="lace"),
        LineProgram(kind="unsupported", unsupported_reason="chain spaces"),
    )


def test_canonical_repeat_of_one_unwrapped():
    assert programs_equal(rnd("R", Repeat(times=1, body=[sc(2), inc()])), rnd("R", sc(2), inc()))
