"""Record the fine-tuned model's real answers for the app's sample inputs, for demo mode.

    llama-server ... (the local StitchProof model)
    python -m stitchproof.app.record_demo

Writes data/demo/recorded.jsonl: one line per prompt with the model's raw output. Demo mode
(STITCHPROOF_BACKEND=replay) replays these for exactly the same prompts, so the app can be
tried with genuine model output when the local model isn't running. Inputs are the app's own sample
pattern (frontend/src/lib/example.ts), the same pattern with Rnd 5 fixed, and the maker-mode rows.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..prompts import messages_for_line
from ..segment import segment
from .local_model import LlamaServerBackend

EXAMPLE_TS = Path("frontend/src/lib/example.ts")
OUT = Path("data/demo/recorded.jsonl")
MAKER_HEADER = "US terms"  # what check_row uses
MAKER_ROWS = ["Rnd 5: (sc 3, inc) x6 (31)", "Rnd 5: (sc 3, inc) x6 (30)"]


def sample_pattern() -> str:
    m = re.search(r"EXAMPLE = `(.*?)`;", EXAMPLE_TS.read_text(), re.S)
    if not m:
        raise SystemExit(f"couldn't find the sample pattern in {EXAMPLE_TS}")
    return m.group(1)


def prompts() -> list[list[dict]]:
    text = sample_pattern()
    fixed = text.replace("Rnd 5: (sc 3, inc) x6 (31)", "Rnd 5: (sc 3, inc) x6 (30)")
    out = []
    for t in (text, fixed):
        seg = segment(t)
        out += [messages_for_line(seg.header, l.prev_text, l.text) for l in seg.lines]
    out += [messages_for_line(MAKER_HEADER, None, r) for r in MAKER_ROWS]
    seen, unique = set(), []
    for m in out:
        k = m[-1]["content"]
        if k not in seen:
            seen.add(k)
            unique.append(m)
    return unique


def main() -> None:
    backend = LlamaServerBackend()
    rows = []
    for m in prompts():
        rows.append({"user": m[-1]["content"], "output": backend.complete(m)})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    print(f"recorded {len(rows)} answers from {backend.name} to {OUT}")


if __name__ == "__main__":
    main()
