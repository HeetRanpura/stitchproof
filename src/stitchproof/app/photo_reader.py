"""Read a photo or scan of a printed pattern with a local Gemma 4 vision model (Ollama).

The image is transcribed to plain text, which then goes through the normal StitchProof
pipeline. Gemma only transcribes: it never interprets or checks stitches. If Ollama or the
model isn't available, the caller falls back to "please paste the text".

    ollama pull gemma4:e4b-it-qat
    STITCHPROOF_VISION_MODEL=gemma4:e4b-it-qat   # default
"""
from __future__ import annotations

import base64
import json
import os
import urllib.request
from pathlib import Path

IMAGE_TYPES = (".png", ".jpg", ".jpeg", ".webp")
DEFAULT_MODEL = "gemma4:e4b-it-qat"

PROMPT = """Transcribe this crochet pattern exactly as printed, one printed line per output line.
Keep every word, number, abbreviation, bracket, asterisk and punctuation mark exactly as written, even if a number looks wrong.
Do not correct, explain, summarise, translate or add anything. Do not use Markdown formatting.
If a line is cut off or unreadable, copy what you can read.
Output only the transcribed text."""


class PhotoReaderUnavailable(RuntimeError):
    pass


def _url() -> str:
    return os.environ.get("STITCHPROOF_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")


def model_name() -> str:
    return os.environ.get("STITCHPROOF_VISION_MODEL", DEFAULT_MODEL)


def status() -> tuple[bool, str]:
    """Is the local Gemma model available? Sends no image."""
    try:
        tags = json.loads(urllib.request.urlopen(f"{_url()}/api/tags", timeout=3).read())
    except Exception:  # noqa: BLE001
        return False, "Ollama isn't running"
    names = {m["name"] for m in tags.get("models", [])}
    if model_name() not in names and f"{model_name()}:latest" not in names:
        return False, f"Ollama has no {model_name()} (run: ollama pull {model_name()})"
    return True, f"{model_name()} (local)"


def _clean(text: str) -> str:
    lines = []
    for line in text.strip().splitlines():
        s = line.rstrip()
        if s.strip().startswith("```"):
            continue
        lines.append(s)
    return "\n".join(lines).strip()


def transcribe(image_path: str | Path, timeout: float = 300) -> str:
    ok, why = status()
    if not ok:
        raise PhotoReaderUnavailable(why)
    img = base64.b64encode(Path(image_path).read_bytes()).decode()
    body = {
        "model": model_name(),
        "messages": [{"role": "user", "content": PROMPT, "images": [img]}],
        "stream": False,
        "think": False,
        "options": {"temperature": 0, "num_predict": 2048},
    }
    req = urllib.request.Request(f"{_url()}/api/chat", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read())
    return _clean(out["message"]["content"])
