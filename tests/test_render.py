import random
import re

import pytest

from stitchproof.generate import render, shapes
from stitchproof.generate.render import HELDOUT, sample_style, uses_heldout
from stitchproof.schema import LineKind
from stitchproof.segment import segment
from stitchproof.simulate import Status, simulate

ALL_SHAPES = shapes.TRAIN_SHAPES + shapes.EVAL_ONLY_SHAPES


def test_training_styles_never_use_heldout_options():
    rng = random.Random(0)
    for _ in range(500):
        assert not uses_heldout(sample_style(rng, heldout=False))


def test_eval_styles_use_all_heldout_options():
    rng = random.Random(0)
    for _ in range(50):
        st = sample_style(rng, heldout=True)
        assert all(getattr(st, k) == v for k, v in HELDOUT.items())


def test_per_line_switching_never_picks_heldout_in_training():
    rng = random.Random(3)
    for i in range(60):
        pat = shapes.generate(rng, rng.choice(shapes.TRAIN_SHAPES), f"t{i}")
        r = render.render(pat, sample_style(rng), rng)
        for t in r.texts:
            assert "more time" not in t and "should have" not in t.lower() and "each of the next" not in t
            assert not re.match(r"^(Round|Row)s? [\d\- to]+ - ", t), t


@pytest.mark.parametrize("shape", ALL_SHAPES)
def test_every_shape_renders_clean_and_aligned(shape):
    rng = random.Random(shape)
    for i in range(40):
        pat = shapes.generate(rng, shape, f"{shape}{i}")
        assert 6 <= len(pat.lines) <= 25
        r = render.render(pat, sample_style(rng, heldout=i % 2 == 0), rng)
        assert len(r.texts) == len(r.programs) == len(segment(r.text).lines)
        res = simulate(r.programs)
        assert not [x for x in res if x.status == Status.ERROR], r.text
        for p, t in zip(r.programs, r.texts):
            if p.kind in (LineKind.ROW, LineKind.ROUND):
                assert p.label and t.startswith(p.label.split("-")[0].split(" to ")[0]), (p.label, t)


def test_cone_is_eval_only():
    assert "cone" not in shapes.TRAIN_SHAPES


def test_stated_count_written_in_text():
    rng = random.Random(7)
    for i in range(50):
        pat = shapes.generate(rng, rng.choice(ALL_SHAPES), f"s{i}")
        r = render.render(pat, sample_style(rng), rng)
        for p, t in zip(r.programs, r.texts):
            if p.stated_count is not None:
                assert str(p.stated_count) in t


def test_more_times_style_means_n_plus_one():
    rng = random.Random(1)
    pat = shapes.generate(rng, "sphere", "x")
    st = sample_style(rng, heldout=True)
    r = render.render(pat, st, rng, heldout=True)
    assert any("more times" in t for t in r.texts)
    assert not [x for x in simulate(r.programs) if x.status == Status.ERROR]
