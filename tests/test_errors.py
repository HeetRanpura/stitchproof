import random

import pytest

from stitchproof.generate import errors, shapes
from stitchproof.generate.build_dataset import make_pattern, TRAIN_MIX
from stitchproof.simulate import Status, simulate


def _pattern(shape, seed):
    rng = random.Random(seed)
    return shapes.generate(rng, shape, f"{shape}-{seed}"), rng


@pytest.mark.parametrize(
    "etype,shape",
    [
        ("WRONG_STATED", "sphere"),
        ("WRONG_REPEAT_TIMES", "sphere"),
        ("WRONG_RUN_LENGTH", "mixed"),
        ("WRONG_FOUNDATION", "rectangle"),
        ("NON_DIVISIBLE_AROUND", "sphere"),
    ],
)
def test_each_seeder_produces_a_flag(etype, shape):
    hits = 0
    for seed in range(40):
        pat, rng = _pattern(shape, seed)
        e = errors.SEEDERS[etype](pat, rng)
        if e is None:
            continue
        res = simulate([gl.program for gl in pat.lines])
        if res[e.line].status == Status.ERROR:
            hits += 1
    assert hits >= 10, f"{etype} rarely produces a detectable error ({hits})"


def test_seed_flags_exactly_the_seeded_lines():
    for seed in range(60):
        pat, rng = _pattern(random.Random(seed).choice(shapes.TRAIN_SHAPES), seed)
        out = errors.seed(pat, rng, n_errors=1 + seed % 2)
        if out is None:
            continue
        seeded_pat, errs = out
        flagged = {r.index for r in simulate([gl.program for gl in seeded_pat.lines]) if r.status == Status.ERROR}
        assert flagged == {e.line for e in errs}
        assert not errors.error_lines(pat), "the original must stay clean (seed works on a copy)"


def test_missing_stated_is_a_warning():
    pat, rng = _pattern("sphere", 2)
    dropped = errors.drop_stated_counts(pat, rng, p_line=1.0)
    assert dropped
    res = simulate([gl.program for gl in pat.lines])
    assert all(res[d.line].status == Status.WARNING for d in dropped)


def test_pattern_records_have_consistent_labels():
    for i in range(30):
        rec = make_pattern("test", i, TRAIN_MIX, heldout=False)
        assert set(rec["error_lines"]) == {e["line"] for e in rec["seeded_errors"]}
        assert len(rec["lines"]) == len(rec["text"].splitlines())


def test_build_is_reproducible():
    a = make_pattern("test", 5, TRAIN_MIX, heldout=False)
    b = make_pattern("test", 5, TRAIN_MIX, heldout=False)
    assert a == b
