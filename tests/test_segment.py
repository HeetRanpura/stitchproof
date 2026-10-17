from stitchproof.segment import build_header, looks_like_row, segment

PATTERN = """Tiny Ball
US terms, worked in spiral rounds.

Rnd 1: 6 sc in MR (6)
- Place a stitch marker.
Rnd 2: inc x6 (12)
R3: (sc, inc) x6 (18)
4) (sc 2, inc) x6 (24)
"""


def test_segment_lines_and_prev():
    s = segment(PATTERN)
    texts = [l.text for l in s.lines]
    assert texts[0] == "Tiny Ball"
    assert "Place a stitch marker." in texts
    assert s.lines[3].prev_text == s.lines[2].text
    assert s.lines[0].prev_text is None


def test_header():
    h = build_header(PATTERN)
    assert h == "Title: Tiny Ball | US terms | worked in spiral rounds"
    assert build_header("Rnd 1: 6 sc in MR (6)") == "(no header)"
    assert "UK terms" in build_header("Bear\nUK terms\nR1: 6 dc in MR")


def test_looks_like_row():
    for t in ["Rnd 1: 6 sc", "R12: sc around", "Row 3: sc across", "4) sc", "Round 5 - sc", "Rnds 5-10: sc"]:
        assert looks_like_row(t), t
    for t in ["Stuff firmly.", "Materials: 4 mm hook", "*sc, inc* around"]:
        assert not looks_like_row(t), t


def test_bullet_star_repeat_not_stripped():
    s = segment("*sc, inc* 6 times (18)")
    assert s.lines[0].text == "*sc, inc* 6 times (18)"


def test_merge_wrapped_pdf_lines():
    s = segment("Rnd 5: sc 3, inc, sc 3, inc, sc 3,\ninc, sc 3, inc (30)\nStuff.", merge_wrapped=True)
    assert len(s.lines) == 2 and s.lines[0].text.endswith("inc (30)")
