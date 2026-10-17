"""Local-vs-Tinker equivalence check for the exported model.

    llama-server -m models/stitchproof-base-q4_k_m.gguf --lora models/stitchproof-lora-v1.gguf --port 8080
    python -m stitchproof.eval.equivalence --n 50

Runs the same N val lines (fixed seed) through the local llama.cpp server and through the
fine-tuned model on Tinker (temperature 0, same prompt and parser), and reports how often the
canonicalised programs agree. Also reports per-line latency and the GGUF sizes.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import time
from pathlib import Path

from ..canonical import programs_equal
from ..parse_output import parse_model_output
from ..prompts import messages_for_line
from ..tinker_io import BASE_MODEL, Sampler

VAL = Path("data/generated/val_patterns.jsonl")
OUT = Path("eval/results/equivalence.json")


def sample_lines(n: int, seed: int = 0) -> list[tuple[str, str | None, str]]:
    items = []
    for rec in (json.loads(l) for l in VAL.read_text().splitlines() if l.strip()):
        for line in rec["lines"]:
            items.append((rec["header"], line["prev"], line["text"]))
    return random.Random(seed).sample(items, min(n, len(items)))


def local_complete(messages: list[dict], url: str = "http://127.0.0.1:8080") -> str:
    import urllib.request

    body = {"messages": messages, "temperature": 0, "max_tokens": 400, "chat_template_kwargs": {"enable_thinking": False}}
    req = urllib.request.Request(f"{url}/v1/chat/completions", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"] or ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--label", default="q4_k_m")
    args = ap.parse_args()
    items = sample_lines(args.n)
    msgs = [messages_for_line(*it) for it in items]

    t0 = time.time()
    local_out = []
    lat = []
    for m in msgs:
        s = time.time()
        local_out.append(local_complete(m))
        lat.append(time.time() - s)
    total_local = time.time() - t0

    runs = json.loads(Path("train/runs.json").read_text())
    sampler = Sampler(model=BASE_MODEL, model_path=runs["final"]["sampler_path"])
    remote_out = asyncio.run(sampler.complete_many(msgs))

    agree = 0
    rows = []
    for it, lo, ro in zip(items, local_out, remote_out):
        lp, rp = parse_model_output(lo).program, parse_model_output(ro).program
        same = (lp is None and rp is None) or programs_equal(lp, rp)
        agree += same
        rows.append({"line": it[2], "local": lo, "tinker": ro, "agree": same})
    lat_sorted = sorted(lat)
    result = {
        "label": args.label,
        "n": len(items),
        "agree": agree,
        "agreement_pct": round(100 * agree / len(items), 1),
        "latency_s": {"mean": round(sum(lat) / len(lat), 3), "p50": round(lat_sorted[len(lat) // 2], 3), "max": round(lat_sorted[-1], 3), "total": round(total_local, 1)},
        "gguf_sizes_gb": {p.name: round(p.stat().st_size / 1e9, 2) for p in Path("models").glob("stitchproof-*.gguf")},
        "tinker_usage": sampler.usage.__dict__,
        "rows": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out = OUT.with_name(f"equivalence_{args.label}.json")
    out.write_text(json.dumps(result, indent=1))
    print(f"agreement {result['agreement_pct']}% ({agree}/{len(items)}); latency mean {result['latency_s']['mean']}s, p50 {result['latency_s']['p50']}s; saved {out}")


if __name__ == "__main__":
    main()
