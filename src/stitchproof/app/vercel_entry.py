"""Vercel entrypoint for the `app` service (FastAPI).

Vercel can't run the local model (llama.cpp) or Gemma (Ollama), so the hosted app runs in
demo mode: it replays the fine-tuned model's recorded answers for the sample pattern
(data/demo/recorded.jsonl) and says so in the UI. Patterns that aren't samples come back as
"can't check" with a pointer to installing StitchProof locally.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
os.chdir(ROOT)  # data files are read relative to the repo root
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

os.environ.setdefault("STITCHPROOF_BACKEND", "replay")
os.environ.setdefault("STITCHPROOF_CACHE", "/tmp/stitchproof_cache")  # the only writable place on Vercel
os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

from stitchproof.app.server import app  # noqa: E402

__all__ = ["app"]
