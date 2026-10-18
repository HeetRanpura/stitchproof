"""Local web app API (FastAPI TestClient, replay backend, temp cache). No model or network needed."""
import io
import json

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from stitchproof.app import local_model, photo_reader, server  # noqa: E402
from stitchproof.generate.build_dataset import EVAL_MIX, make_pattern  # noqa: E402
from test_pdf import _pdf  # noqa: E402
from test_photo_reader import _fake_urlopen  # noqa: E402


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(local_model, "CACHE_DIR", tmp_path)
    monkeypatch.setenv("STITCHPROOF_BACKEND", "replay")
    server.parser.cache_clear()
    rec = next(r for r in (make_pattern("srvtest", i, EVAL_MIX, heldout=True) for i in range(50)) if r["seeded_errors"])
    backend = local_model.ReplayBackend(files=[])
    backend.is_demo = False  # stands in for a local install
    backend.gold = {l["text"]: json.dumps(l["gold"]) for l in rec["lines"]}
    monkeypatch.setattr(server, "parser", lambda: local_model.LineParser(backend))
    c = TestClient(server.app)
    c.rec = rec
    return c


def _events(body: str):
    out = []
    for block in body.strip().split("\n\n"):
        ev = dict(line.split(": ", 1) for line in block.splitlines())
        out.append((ev["event"], json.loads(ev["data"])))
    return out


def test_status(client):
    r = client.get("/api/status").json()
    assert r["model"]["demo"] is False and r["model"]["local"] is True
    assert "photo_reader" in r and "ready" in r["photo_reader"]


def test_check_flags_seeded_errors(client):
    r = client.post("/api/check", json={"text": client.rec["text"]}).json()
    flagged = {l["index"] for l in r["lines"] if l["status"] == "ERROR"}
    assert flagged == set(client.rec["error_lines"])
    assert r["counts"]["ERROR"] == len(flagged)
    assert all("explanation" in l and "text" in l for l in r["lines"])


def test_stream_matches_check(client):
    body = client.post("/api/check/stream", json={"text": client.rec["text"]}).text
    ev = _events(body)
    assert ev[0][0] == "start" and ev[-1][0] == "done"
    lines = [d for k, d in ev if k == "line"]
    assert len(lines) == len(ev[0][1]["lines"])
    full = client.post("/api/check", json={"text": client.rec["text"]}).json()
    assert [l["status"] for l in lines] == [l["status"] for l in full["lines"]]
    assert [l["explanation"] for l in lines] == [l["explanation"] for l in full["lines"]]


def test_empty_text_rejected(client):
    assert client.post("/api/check", json={"text": "  "}).status_code == 400


def test_upload_text_and_pdf(client):
    r = client.post("/api/upload", files={"file": ("p.md", b"# Ball\nRnd 1: 6 sc in MR (6)\n")}).json()
    assert r["source"] == "text" and "Rnd 1" in r["text"]
    r = client.post("/api/upload", files={"file": ("p.pdf", _pdf(["Rnd 1: 6 sc in MR (6)", "Rnd 2: inc x6 (12)"]))}).json()
    assert r["source"] == "pdf" and "Rnd 2: inc x6 (12)" in r["text"] and r["merge_wrapped"] is True


def test_upload_unsupported_and_scan_pdf(client):
    assert client.post("/api/upload", files={"file": ("p.docx", b"x")}).status_code == 422
    r = client.post("/api/upload", files={"file": ("scan.pdf", _pdf([]))})
    assert r.status_code == 422 and "text layer" in r.json()["detail"]["message"]


def test_upload_photo_via_gemma_and_fallback(client, monkeypatch):
    monkeypatch.setattr(photo_reader.urllib.request, "urlopen", _fake_urlopen([photo_reader.DEFAULT_MODEL], "Rnd 1: 6 sc in MR (6)", []))
    r = client.post("/api/upload", files={"file": ("p.jpg", io.BytesIO(b"\xff\xd8"))}).json()
    assert r["source"] == "photo" and r["transcribed_by"] == photo_reader.DEFAULT_MODEL
    monkeypatch.setattr(photo_reader.urllib.request, "urlopen", _fake_urlopen(None, "", []))
    r = client.post("/api/upload", files={"file": ("p.png", io.BytesIO(b"\x89PNG"))})
    assert r.status_code == 422 and "paste the pattern text" in r.json()["detail"]["message"]


def test_row_maker_mode(client, monkeypatch):
    backend = local_model.ReplayBackend(files=[])
    backend.gold = {"Rnd 5: (sc 3, inc) x6 (31)": '{"kind":"round","label":"Rnd 5","ops":[{"t":"repeat","times":6,"body":[{"t":"work","stitch":"sc","n":3},{"t":"into_one","stitch":"sc","k":2}]}],"stated_count":31}'}
    monkeypatch.setattr(server, "parser", lambda: local_model.LineParser(backend))
    r = client.post("/api/row", json={"previous_count": 24, "row": "Rnd 5: (sc 3, inc) x6 (31)"}).json()
    assert r["answer"].startswith("The pattern says 31. These instructions make 30 from your 24 stitches.")
    assert r["result"]["status"] == "ERROR"


def test_reports(client):
    md = client.post("/api/report?format=md", json={"text": client.rec["text"]})
    assert md.status_code == 200 and "attachment" in md.headers["content-disposition"] and "# StitchProof report" in md.text
    html = client.post("/api/report?format=html", json={"text": client.rec["text"]})
    assert "<html" in html.text and "Your pattern never leaves it" in html.text
    assert client.post("/api/report?format=pdf", json={"text": "x"}).status_code == 400


def test_unknown_api_404_and_spa_fallback(client):
    assert client.get("/api/nope").status_code == 404
    r = client.get("/some/deep/link")
    assert r.status_code in (200, 503)


def test_binds_localhost_only():
    assert server.HOST == "127.0.0.1"


def test_demo_mode_replays_recorded_model_answers(monkeypatch, tmp_path):
    """Demo mode (no model running): recorded fine-tuned answers for the sample pattern."""
    import re
    from pathlib import Path

    monkeypatch.setattr(local_model, "CACHE_DIR", tmp_path / "cache")
    backend = local_model.ReplayBackend()
    monkeypatch.setattr(server, "parser", lambda: local_model.LineParser(backend))
    c = TestClient(server.app)

    st = c.get("/api/status").json()
    assert st["model"]["demo"] is True and st["model"]["ready"] is True
    assert st["photo_reader"]["ready"] is False
    r = c.post("/api/upload", files={"file": ("p.jpg", io.BytesIO(b"\xff\xd8"))})
    assert r.status_code == 422 and "demo mode" in r.json()["detail"]["message"].lower()

    example = re.search(r"EXAMPLE = `(.*?)`;", Path("frontend/src/lib/example.ts").read_text(), re.S).group(1)
    r = c.post("/api/check", json={"text": example}).json()
    assert [l["label"] for l in r["lines"] if l["status"] == "ERROR"] == ["Rnd 5", "Rnd 11"]

    fixed = example.replace("(31)", "(30)")
    r = c.post("/api/check", json={"text": fixed}).json()
    assert [l["label"] for l in r["lines"] if l["status"] == "ERROR"] == ["Rnd 11"]

    r = c.post("/api/row", json={"previous_count": 24, "row": "Rnd 5: (sc 3, inc) x6 (31)"}).json()
    assert "not you" in r["answer"]

    r = c.post("/api/check", json={"text": "Rnd 1: 7 sc in MR (7)"}).json()
    assert r["lines"][0]["status"] == "CAN'T CHECK" and "local model" in r["lines"][0]["explanation"]
