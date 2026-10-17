"""Gemma photo reader: request shape, cleanup, and fallback when Ollama/Gemma is missing (Ollama mocked)."""
import io
import json

import pytest

from stitchproof.app import photo_reader


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _fake_urlopen(tags, reply, seen):
    def urlopen(req, timeout=None):
        url = req if isinstance(req, str) else req.full_url
        if url.endswith("/api/tags"):
            if tags is None:
                raise OSError("connection refused")
            return _Resp(json.dumps({"models": [{"name": t} for t in tags]}).encode())
        seen.append(json.loads(req.data))
        return _Resp(json.dumps({"message": {"content": reply}}).encode())

    return urlopen


def test_transcribe_sends_image_and_cleans_fences(monkeypatch, tmp_path):
    img = tmp_path / "p.jpg"
    img.write_bytes(b"\xff\xd8fakejpeg")
    seen = []
    monkeypatch.setattr(photo_reader.urllib.request, "urlopen", _fake_urlopen([photo_reader.DEFAULT_MODEL], "```\nRnd 1: 6 sc in MR (6)\nRnd 2: inc x6 (12)\n```", seen))
    text = photo_reader.transcribe(img)
    assert text == "Rnd 1: 6 sc in MR (6)\nRnd 2: inc x6 (12)"
    body = seen[0]
    assert body["model"] == photo_reader.DEFAULT_MODEL and body["options"]["temperature"] == 0
    assert body["messages"][0]["images"] and "exactly as printed" in body["messages"][0]["content"]


def test_unavailable_when_ollama_down(monkeypatch, tmp_path):
    monkeypatch.setattr(photo_reader.urllib.request, "urlopen", _fake_urlopen(None, "", []))
    ok, why = photo_reader.status()
    assert not ok and "isn't running" in why
    with pytest.raises(photo_reader.PhotoReaderUnavailable):
        photo_reader.transcribe(tmp_path / "x.png")


def test_unavailable_when_model_missing(monkeypatch):
    monkeypatch.setattr(photo_reader.urllib.request, "urlopen", _fake_urlopen(["llama3:latest"], "", []))
    ok, why = photo_reader.status()
    assert not ok and "ollama pull" in why


def test_ui_falls_back_to_paste_message(monkeypatch, tmp_path):
    gr = pytest.importorskip("gradio")
    from stitchproof.app.ui import read_upload

    monkeypatch.setattr(photo_reader.urllib.request, "urlopen", _fake_urlopen(None, "", []))
    img = tmp_path / "pattern.png"
    img.write_bytes(b"\x89PNG")
    with pytest.raises(gr.Error):
        read_upload(str(img))


def test_ui_reads_photo_via_gemma(monkeypatch, tmp_path):
    pytest.importorskip("gradio")
    from stitchproof.app.ui import read_upload

    monkeypatch.setattr(photo_reader.urllib.request, "urlopen", _fake_urlopen([photo_reader.DEFAULT_MODEL], "Rnd 1: 6 sc in MR (6)", []))
    img = tmp_path / "pattern.jpeg"
    img.write_bytes(b"\xff\xd8")
    text, merge = read_upload(str(img))
    assert text == "Rnd 1: 6 sc in MR (6)" and merge is True
