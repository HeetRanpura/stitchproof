"""Teacher rewrite of ~35% of train/val patterns into a natural designer voice (Tinker).

    python -m stitchproof.generate.paraphrase --dry-run   # cost estimate only
    python -m stitchproof.generate.paraphrase             # writes data/generated/paraphrased.jsonl
    python -m stitchproof.generate.build_dataset --paraphrased data/generated/paraphrased.jsonl

Constraints checked in code for every rewrite: same number of lines, every row label kept at
the start of its line, every number of the original line still present, and no new numbers
other than 1 and 2 (so "inc" may become "2 sc in the next stitch", but nothing is recounted).
Failures are retried up to 3 times, then the pattern stays template-rendered.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from ..tinker_io import TEACHER_MODEL, Sampler, estimate_tokens
from .build_dataset import OUT, read_jsonl, write_jsonl

SHARE = 0.35
CACHE = OUT / "paraphrased.jsonl"
PRICES = (0.30, 0.90)  # US$/M prompt, completion for the teacher (estimate only; check the console)

SYSTEM = """You rewrite crochet patterns in a warm, natural designer voice, like a pattern sold on Etsy.
Rules:
- Output exactly the same number of lines as the input, one rewritten line per input line, in the same order. No blank lines, no extra headings, no commentary.
- Start every row or round line with exactly the same label as the input line (for example "Rnd 3:", "R7.", "Rows 2-5:").
- Keep every number from the input line. You may spell out abbreviations, explain a stitch in words, or add a short tip, but never change, add or recount any stitch or number.
- Do not fix anything, even if a stitch count looks wrong. Copy stated counts exactly.
- Keep the meaning of each line identical. Keep notes as notes."""

_NUM = re.compile(r"\d+")


def selected(pid: str) -> bool:
    return int(hashlib.sha1(pid.encode()).hexdigest(), 16) % 1000 < SHARE * 1000


def _label_prefix(gold: dict) -> str | None:
    return gold.get("label") if gold.get("kind") in ("row", "round", "unsupported") else None


def validate(rec: dict, new_lines: list[str]) -> str | None:
    """Return None if the rewrite is acceptable, else the reason it isn't."""
    if len(new_lines) != len(rec["lines"]):
        return f"line count {len(new_lines)} != {len(rec['lines'])}"
    for i, (old, new) in enumerate(zip(rec["lines"], new_lines)):
        lab = _label_prefix(old["gold"])
        if lab and not new.strip().lower().startswith(lab.lower()):
            return f"line {i}: label {lab!r} missing"
        before = Counter(_NUM.findall(old["text"]))
        after = Counter(_NUM.findall(new))
        missing = before - after
        if missing:
            return f"line {i}: numbers {sorted(missing)} missing"
        extra = {n for n in (after - before) if n not in ("1", "2")}
        if extra:
            return f"line {i}: new numbers {sorted(extra)}"
    return None


def _messages(rec: dict, feedback: str | None = None) -> list[dict]:
    user = "Rewrite this pattern:\n\n" + "\n".join(l["text"] for l in rec["lines"])
    if feedback:
        user += f"\n\nYour previous attempt was rejected ({feedback}). Follow the rules exactly."
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def _split_lines(text: str) -> list[str]:
    lines = [l.strip() for l in text.strip().splitlines()]
    lines = [l for l in lines if l and not l.startswith("```")]
    return [re.sub(r"^\s*[-•]\s+", "", l) for l in lines]


async def run(records: list[dict], sampler: Sampler) -> list[dict]:
    async def one(rec):
        feedback = None
        for attempt in range(3):
            raw = await sampler.complete(_messages(rec, feedback), cache=True)
            lines = _split_lines(raw)
            feedback = validate(rec, lines)
            if feedback is None:
                return {"id": rec["id"], "ok": True, "attempts": attempt + 1, "lines": lines}
        return {"id": rec["id"], "ok": False, "reason": feedback}

    return await asyncio.gather(*(one(r) for r in records))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-usd", type=float, default=5.0)
    args = ap.parse_args()
    recs = [r for split in ("train", "val") for r in read_jsonl(OUT / f"{split}_patterns.jsonl") if selected(r["id"])]
    p_tok, c_tok = estimate_tokens(TEACHER_MODEL, [_messages(r) for r in recs], 2500)
    est = (p_tok / 1e6 * PRICES[0] + c_tok / 1e6 * PRICES[1]) * 1.5  # allow for retries
    print(f"{len(recs)} patterns selected for paraphrase; about {p_tok:,} prompt + up to {c_tok:,} completion tokens per pass; about US${est:.2f} with retries")
    if args.dry_run:
        return
    if est > args.max_usd:
        raise SystemExit("over budget; stopping")
    sampler = Sampler(model=TEACHER_MODEL, max_tokens=4000, temperature=0.7, concurrency=16)
    results = asyncio.run(run(recs, sampler))
    write_jsonl(CACHE, results)
    ok = sum(r["ok"] for r in results)
    print(f"paraphrased {ok}/{len(results)} patterns; usage {sampler.usage}")
    fails = Counter(r["reason"].split(":")[-1].split("[")[0].strip() for r in results if not r["ok"])
    if fails:
        print("rejections:", dict(fails))


if __name__ == "__main__":
    main()
