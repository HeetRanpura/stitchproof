"""label_real must refuse unsafe contexts. (No real patterns are used in tests.)"""
import pytest

from stitchproof.eval import label_real


def test_refuses_in_ci(monkeypatch, tmp_path):
    monkeypatch.setenv("CI", "true")
    with pytest.raises(SystemExit, match="CI"):
        label_real.guard(label_real.REAL_DIR / "x.txt")


def test_refuses_without_terminal(monkeypatch):
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    # pytest captures stdin/stdout, so they are not TTYs here
    with pytest.raises(SystemExit, match="interactive terminal"):
        label_real.guard(label_real.REAL_DIR / "x.txt")


def test_refuses_files_outside_data_real(monkeypatch, tmp_path):
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setattr(label_real.sys.stdin, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(label_real.sys.stdout, "isatty", lambda: True, raising=False)
    with pytest.raises(SystemExit, match="data/real"):
        label_real.guard(tmp_path / "draft.txt")


def test_pattern_id_is_a_content_hash():
    a = label_real.pattern_id("Designer Name's Bear\nRnd 1: 6 sc in MR (6)")
    assert a.startswith("real-") and "Bear" not in a and len(a) == 17
    assert a == label_real.pattern_id("Designer Name's Bear\nRnd 1: 6 sc in MR (6)")


def test_real_dir_is_gitignored():
    import subprocess

    r = subprocess.run(["git", "check-ignore", "-q", "data/real/anything.txt"])
    assert r.returncode == 0


def test_label_flow_on_synthetic_pattern(monkeypatch, tmp_path):
    """Scripted run on a synthetic eval pattern with the replay backend, in a temp dir."""
    import json

    from stitchproof.app import local_model

    rec = json.loads(open("data/generated/eval_synth.jsonl").readline())
    real = tmp_path / "real"
    real.mkdir()
    draft = real / "draft.txt"
    draft.write_text(rec["text"])
    monkeypatch.setattr(label_real, "REAL_DIR", real)
    monkeypatch.setattr(label_real, "OUT", real / "real_labelled.jsonl")
    monkeypatch.setattr(local_model, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setenv("STITCHPROOF_BACKEND", "replay")
    answers = iter(["a"] * len(rec["lines"]))
    monkeypatch.setattr("builtins.input", lambda *_: next(answers))
    label_real.label(draft)
    out = [json.loads(l) for l in (real / "real_labelled.jsonl").read_text().splitlines()]
    assert len(out) == 1 and out[0]["id"].startswith("real-")
    assert out[0]["error_lines"] == rec["error_lines"]
    assert [l["gold"] for l in out[0]["lines"]] == [l["gold"] for l in rec["lines"]]
