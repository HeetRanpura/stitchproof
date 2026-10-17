import json

import pytest

from stitchproof.app import local_model
from stitchproof.app.local_model import Backend, LineParser, check_pattern, check_row
from stitchproof.app.report_export import summary_line, table_rows, to_html, to_markdown
from stitchproof.generate.build_dataset import EVAL_MIX, make_pattern
from stitchproof.schema import LineProgram, to_compact_json


class GoldBackend(Backend):
    """Answers with gold programs for one known pattern, and counts calls."""

    name = "gold-test"
    concurrency = 1

    def __init__(self, records):
        self.gold = {l["text"]: to_compact_json(LineProgram.model_validate(l["gold"])) for r in records for l in r["lines"]}
        self.calls = 0

    def complete(self, messages):
        self.calls += 1
        return self.gold.get(messages[-1]["content"].split("\nLine: ", 1)[-1], "not json")


@pytest.fixture(autouse=True)
def tmp_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(local_model, "CACHE_DIR", tmp_path)


def _error_record():
    for i in range(50):
        rec = make_pattern("apptest", i, EVAL_MIX, heldout=True)
        if rec["seeded_errors"]:
            return rec
    raise AssertionError


def test_check_pattern_flags_seeded_errors_and_caches():
    rec = _error_record()
    backend = GoldBackend([rec])
    parser = LineParser(backend)
    check = check_pattern(rec["text"], parser)
    flagged = {r.index for r in check.results if r.status.value == "ERROR"}
    assert flagged == set(rec["error_lines"])
    n = backend.calls
    check_pattern(rec["text"], parser)  # second run is served from the cache
    assert backend.calls == n


def test_reports_render_and_escape():
    rec = _error_record()
    check = check_pattern(rec["text"] + "\n<script>alert(1)</script>", LineParser(GoldBackend([rec])))
    md = to_markdown(check)
    html = to_html(check)
    assert "error" in summary_line(check)
    assert "## Rows to look at" in md
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html
    assert "Your pattern never leaves it" in html
    assert len(table_rows(check)) == sum(1 for r in check.results if r.status.value != "NOTE")


def test_check_row_maker_mode():
    rec = {"lines": [{"text": "Rnd 5: (sc 3, inc) x6 (31)", "gold": json.loads('{"kind":"round","label":"Rnd 5","ops":[{"t":"repeat","times":6,"body":[{"t":"work","stitch":"sc","n":3},{"t":"into_one","stitch":"sc","k":2}]}],"stated_count":31}')}]}
    answer, res = check_row(24, "Rnd 5: (sc 3, inc) x6 (31)", LineParser(GoldBackend([rec])))
    assert answer.startswith("The pattern says 31. These instructions make 30 from your 24 stitches.")


def test_unreadable_output_is_cant_check():
    check = check_pattern("Rnd 1: 6 sc in MR (6)", LineParser(GoldBackend([])))
    assert check.results[0].status.value == "CAN'T CHECK"
