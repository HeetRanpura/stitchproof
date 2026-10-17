"""Build the synthetic splits (reproducible from a fixed seed).

    python -m stitchproof.generate.build_dataset --pilot          # 40-pattern pilot, templates only
    python -m stitchproof.generate.build_dataset                  # train / val / eval_synth (templates only)
    python -m stitchproof.generate.build_dataset --paraphrased data/generated/paraphrased.jsonl
        # same splits, with the cached teacher rewrites (see paraphrase.py) swapped in

Pattern records (one JSON object per pattern) hold the full text, gold programs, seeded
errors and simulator labels. Training files (train.jsonl / val.jsonl) hold one chat
example per line: header + previous line + current line -> compact program JSON.
"""
from __future__ import annotations

import argparse
import json
import random
from dataclasses import asdict
from pathlib import Path

from ..prompts import SYSTEM_PROMPT, user_message
from ..schema import LineProgram, to_compact_dict, to_compact_json
from ..segment import segment
from ..simulate import Status, simulate
from . import errors, render, shapes

SEED = 20261017
OUT = Path("data/generated")

# Shape mix per split. Cones never appear in train/val.
TRAIN_MIX = {"sphere": 3, "cylinder": 2, "rectangle": 2, "triangle": 1, "trapezoid": 1, "mixed": 1, "two_part": 1}
EVAL_MIX = {"cone": 4, "sphere": 2, "cylinder": 2, "rectangle": 2, "triangle": 1, "trapezoid": 1, "mixed": 1, "two_part": 1}


def _pick(rng: random.Random, mix: dict[str, int]) -> str:
    return rng.choices(list(mix), weights=list(mix.values()))[0]


def _n_errors(rng: random.Random) -> int:
    """About half the patterns are clean; the rest get 1 or 2 errors."""
    r = rng.random()
    return 0 if r < 0.5 else (1 if r < 0.8 else 2)


def make_pattern(split: str, i: int, mix: dict[str, int], heldout: bool) -> dict:
    rng = random.Random(f"{SEED}-{split}-{i}")
    for attempt in range(20):
        shape = _pick(rng, mix)
        pat = shapes.generate(rng, shape, f"{split}-{i:04d}")
        missing = errors.drop_stated_counts(pat, rng)
        n = _n_errors(rng)
        seeded = errors.seed(pat, rng, n)
        if seeded is None:
            continue
        pat, errs = seeded
        style = render.sample_style(rng, heldout=heldout)
        r = render.render(pat, style, rng, heldout=heldout)
        return pattern_record(pat.pid, split, shape, style, r.texts, r.programs, errs, missing)
    raise RuntimeError(f"could not build pattern {split}-{i}")


def pattern_record(pid, split, shape, style, texts, programs, errs, missing, source="template") -> dict:
    labels = simulate(programs)
    text = "\n".join(texts)
    seg = segment(text)
    assert len(seg.lines) == len(programs), pid
    return {
        "id": pid,
        "split": split,
        "shape": shape,
        "source": source,
        "style": asdict(style) if style is not None else None,
        "header": seg.header,
        "text": text,
        "lines": [
            {
                "text": l.text,
                "prev": l.prev_text,
                "gold": to_compact_dict(p),
                "truth": res.status.value,
                "codes": res.codes,
            }
            for l, p, res in zip(seg.lines, programs, labels)
        ],
        "seeded_errors": [e.to_dict() for e in errs],
        "missing_stated": [e.to_dict() for e in missing],
        "error_lines": sorted(r.index for r in labels if r.status == Status.ERROR),
    }


def chat_examples(record: dict) -> list[dict]:
    out = []
    for line in record["lines"]:
        program = LineProgram.model_validate(line["gold"])
        out.append(
            {
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message(record["header"], line["prev"], line["text"])},
                    {"role": "assistant", "content": to_compact_json(program)},
                ],
                "pattern_id": record["id"],
            }
        )
    return out


def write_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    with Path(path).open() as f:
        return [json.loads(l) for l in f if l.strip()]


def build_split(split: str, target_lines: int | None, n_patterns: int | None, mix, heldout: bool) -> list[dict]:
    records, lines, i = [], 0, 0
    while (n_patterns is not None and len(records) < n_patterns) or (target_lines is not None and lines < target_lines):
        rec = make_pattern(split, i, mix, heldout)
        records.append(rec)
        lines += len(rec["lines"])
        i += 1
    return records


def summarise(name: str, records: list[dict]) -> str:
    n_lines = sum(len(r["lines"]) for r in records)
    n_err = sum(len(r["error_lines"]) for r in records)
    clean = sum(1 for r in records if not r["seeded_errors"])
    shapes_ = {}
    for r in records:
        shapes_[r["shape"]] = shapes_.get(r["shape"], 0) + 1
    para = sum(1 for r in records if r["source"] != "template")
    return f"{name}: {len(records)} patterns, {n_lines} lines, {n_err} error lines, {clean} clean patterns, {para} paraphrased, shapes {shapes_}"


def apply_paraphrases(records: list[dict], cache_path: Path) -> list[dict]:
    """Swap in validated teacher rewrites (one text per pattern id) from paraphrase.py's cache."""
    if not cache_path.exists():
        return records
    cache = {r["id"]: r for r in read_jsonl(cache_path) if r.get("ok")}
    out = []
    for rec in records:
        c = cache.get(rec["id"])
        if c is None:
            out.append(rec)
            continue
        programs = [LineProgram.model_validate(l["gold"]) for l in rec["lines"]]
        new = pattern_record(rec["id"], rec["split"], rec["shape"], None, c["lines"], programs, [], [], source="paraphrase")
        new["style"] = rec["style"]
        new["seeded_errors"], new["missing_stated"] = rec["seeded_errors"], rec["missing_stated"]
        out.append(new)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", action="store_true")
    ap.add_argument("--paraphrased", type=Path, default=None)
    ap.add_argument("--train-lines", type=int, default=3000)
    ap.add_argument("--val-lines", type=int, default=300)
    ap.add_argument("--eval-patterns", type=int, default=60)
    args = ap.parse_args()

    if args.pilot:
        recs = build_split("pilot", None, 40, {**TRAIN_MIX, "cone": 2}, heldout=False)
        write_jsonl(OUT / "pilot.jsonl", recs)
        print(summarise("pilot", recs))
        return

    train = build_split("train", args.train_lines, None, TRAIN_MIX, heldout=False)
    val = build_split("val", args.val_lines, None, TRAIN_MIX, heldout=False)
    ev = build_split("eval", None, args.eval_patterns, EVAL_MIX, heldout=True)
    if args.paraphrased:
        train = apply_paraphrases(train, args.paraphrased)
        val = apply_paraphrases(val, args.paraphrased)
    write_jsonl(OUT / "train_patterns.jsonl", train)
    write_jsonl(OUT / "val_patterns.jsonl", val)
    write_jsonl(OUT / "eval_synth.jsonl", ev)
    write_jsonl(OUT / "train.jsonl", [e for r in train for e in chat_examples(r)])
    write_jsonl(OUT / "val.jsonl", [e for r in val for e in chat_examples(r)])
    for name, recs in (("train", train), ("val", val), ("eval_synth", ev)):
        print(summarise(name, recs))


if __name__ == "__main__":
    main()
