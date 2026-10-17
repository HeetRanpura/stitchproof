"""Out-of-generator eval set: our structures and gold, text written by a different model family.

    python -m stitchproof.generate.ood --dry-run
    python -m stitchproof.generate.ood            # writes data/ood/ood.jsonl (25 patterns)

The writer sees only the gold structure as JSON (no rendered text, no style hints from our
renderer) and writes each line in its own words. Validation: one output line per structure
line, the row number at the start of each counted line, and every number in the structure
(counts, repeats, chain lengths, stated counts) present in the line. Failures retry up to 3
times; patterns that still fail are replaced by new ones.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
from collections import Counter
from pathlib import Path

from ..schema import LineProgram
from ..tinker_io import OOD_WRITER_MODEL, Sampler, estimate_tokens
from . import errors, shapes
from .build_dataset import EVAL_MIX, SEED, pattern_record, write_jsonl

OUT = Path("data/ood/ood.jsonl")
N_PATTERNS = 25
FALLBACK_WRITER = "Qwen/Qwen3.5-397B-A17B"
PRICES = (2.205, 5.49)  # Kimi-K2.6 rates from the account billing

SYSTEM = """You are a crochet designer writing up a pattern from a structured outline.
Each outline entry is one line of the pattern. Write exactly one line of pattern text per entry, in the same order, in your own natural style (US terms). No blank lines, headings or commentary beyond the entries.
- "note" entries: write the note text in your own words.
- "foundation" entries: a starting chain of chain_count.
- Row/round entries: begin with a row or round label containing the given row number (or range); write the instructions so they mean exactly the ops given; end with the stated count exactly as given (it may look wrong; do not fix it) or no count if stated_count is absent.
- Op meanings: work = one st in each of the next n; into_one = k sts in one st; together = k sts worked together; work_rest = one st in each remaining st (leave = stop that many before the end); turning_chain = a starting/turning chain (counts_as_stitch says if it counts); repeat = repeat body `times` times (no times = repeat around/to the end); start magic_ring = worked into a magic ring; skip_chains = start in the (skip_chains+1)th chain from the hook.
- Write every number that appears in an entry as digits."""

_NUM = re.compile(r"\d+")


def _entry(gl: shapes.GenLine) -> dict:
    p = gl.program
    if gl.text is not None:
        return {"kind": "note", "text": gl.text}
    d = json.loads(p.model_dump_json(exclude_defaults=True, exclude={"label", "unsupported_reason"}))
    d["kind"] = p.kind.value
    if p.kind.value in ("row", "round", "unsupported"):
        d["row"] = gl.meta.get("row_no") if p.range_start is None else f"{p.range_start}-{p.range_end}"
    if gl.meta.get("joined"):
        d["joined_round"] = True
    if gl.meta.get("lace"):
        d = {"kind": "lace", "row": d.get("row"), "stated_count": p.stated_count, "note": "a chain-space (lace) round/row; write it with ch-1 spaces"}
    return d


def _numbers(entry: dict) -> Counter:
    nums: Counter = Counter()

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k in ("n", "k", "times", "chain_count", "stated_count") and isinstance(v, int):
                    nums[str(v)] += 1
                elif k == "row" and v is not None:
                    for n in _NUM.findall(str(v)):
                        nums[n] += 1
                else:
                    walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    if entry["kind"] != "note":
        walk(entry)
    return nums


def validate(entries: list[dict], lines: list[str]) -> str | None:
    if len(lines) != len(entries):
        return f"line count {len(lines)} != {len(entries)}"
    for i, (e, line) in enumerate(zip(entries, lines)):
        need = _numbers(e)
        have = Counter(_NUM.findall(line))
        # Small numbers (1, 2) are often written as words or implied ("inc"); don't require them.
        missing = {n: c for n, c in (need - have).items() if n not in ("1", "2")}
        if missing:
            return f"line {i}: numbers {sorted(missing)} missing"
        if e["kind"] in ("row", "round", "lace") and not _NUM.match(re.sub(r"^\D*", "", line) or "x"):
            return f"line {i}: no row label"
    return None


def _label_from(line: str) -> str | None:
    m = re.match(r"^\s*((?:rounds?|rnds?|rows?|r)\s*\.?\s*\d+(?:\s*(?:-|–|to)\s*(?:r|row|rnd|round)?\s*\d+)?|\d+(?:\s*-\s*\d+)?(?=\s*[\).:]))", line, re.I)
    return m.group(1).strip() if m else None


def _messages(entries: list[dict], feedback: str | None) -> list[dict]:
    user = "Outline (one JSON entry per line):\n" + "\n".join(json.dumps(e) for e in entries)
    if feedback:
        user += f"\n\nYour previous attempt was rejected ({feedback}). Write exactly {len(entries)} lines."
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def make_structures(n: int) -> list[tuple[shapes.GenPattern, list, list]]:
    out = []
    i = 0
    while len(out) < n:
        rng = random.Random(f"{SEED}-ood-{i}")
        i += 1
        shape = rng.choices(list(EVAL_MIX), weights=list(EVAL_MIX.values()))[0]
        pat = shapes.generate(rng, shape, f"ood-{i:04d}", max_lines=22)
        missing = errors.drop_stated_counts(pat, rng)
        r = rng.random()
        seeded = errors.seed(pat, rng, 0 if r < 0.5 else (1 if r < 0.8 else 2))
        if seeded is None:
            continue
        out.append((seeded[0], seeded[1], missing))
    return out


async def write_all(structs, sampler: Sampler) -> list[dict]:
    async def one(pat, errs, missing):
        entries = [_entry(gl) for gl in pat.lines]
        feedback = None
        for _ in range(3):
            raw = await sampler.complete(_messages(entries, feedback))
            lines = [l.strip() for l in raw.strip().splitlines() if l.strip() and not l.startswith("```")]
            feedback = validate(entries, lines)
            if feedback is None:
                programs = []
                for gl, line in zip(pat.lines, lines):
                    p: LineProgram = gl.program.model_copy(deep=True)
                    if p.kind.value in ("row", "round", "unsupported"):
                        p.label = _label_from(line)
                    programs.append(p)
                rec = pattern_record(pat.pid, "ood", pat.shape, None, lines, programs, errs, missing, source=f"written by {sampler.model}")
                return rec
        return None

    return await asyncio.gather(*(one(*s) for s in structs))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--writer", default=OOD_WRITER_MODEL)
    ap.add_argument("--max-usd", type=float, default=5.0)
    args = ap.parse_args()
    structs = make_structures(N_PATTERNS + 8)  # spares for patterns that fail validation
    msgs = [_messages([_entry(gl) for gl in s[0].lines], None) for s in structs]
    p_tok, c_tok = estimate_tokens(args.writer, msgs, 1500)
    est = (p_tok / 1e6 * PRICES[0] + c_tok / 1e6 * PRICES[1]) * 1.5
    print(f"{len(structs)} structures; about {p_tok:,} prompt + up to {c_tok:,} completion tokens; about US${est:.2f} with retries (writer {args.writer})")
    if args.dry_run:
        return
    if est > args.max_usd:
        raise SystemExit("over budget; stopping")
    sampler = Sampler(model=args.writer, max_tokens=3000, temperature=0.7, concurrency=16)
    recs = [r for r in asyncio.run(write_all(structs, sampler)) if r is not None][:N_PATTERNS]
    write_jsonl(OUT, recs)
    print(f"wrote {len(recs)} OOD patterns to {OUT}; usage {sampler.usage}")


if __name__ == "__main__":
    main()
