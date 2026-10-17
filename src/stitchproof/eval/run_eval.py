"""Run one approach on one eval set and save results.

    python -m stitchproof.eval.run_eval --approach C --set pilot
    python -m stitchproof.eval.run_eval --model base --mode parse --set synth      # same as --approach C

Approaches: A = base model direct check, B = teacher direct check (reference only),
C = base model line parse + simulator, D = fine-tuned model line parse + simulator.
All sampling at temperature 0 with the shared prompts and parser.

For --set real, no pattern text or raw output is ever printed or saved: only statuses and metrics.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

from ..parse_output import parse_model_output, strip_thinking
from ..prompts import direct_messages, messages_for_line
from ..simulate import Status, simulate
from ..tinker_io import BASE_MODEL, TEACHER_MODEL, Sampler, estimate_tokens
from .metrics import PatternPrediction, score

SETS = {
    "pilot": Path("data/generated/pilot.jsonl"),
    "synth": Path("data/generated/eval_synth.jsonl"),
    "ood": Path("data/ood/ood.jsonl"),
    "real": Path("data/real/real_labelled.jsonl"),
}
RESULTS = Path("eval/results")
RUNS = Path("train/runs.json")

APPROACHES = {
    "A": ("base", "direct"),
    "B": ("teacher", "direct"),
    "C": ("base", "parse"),
    "D": ("ft", "parse"),
}

# US$ per million tokens (prompt, completion) for sampling, from the account's Tinker billing rates
# (prompt at the uncached rate, so estimates are an upper bound). Used for the pre-run estimate only.
PRICES = {
    BASE_MODEL: (0.33, 1.005),
    TEACHER_MODEL: (0.33, 0.84),
}


def approach_for(model: str, mode: str) -> str:
    for k, v in APPROACHES.items():
        if v == (model, mode):
            return k
    raise SystemExit(f"no approach for model={model} mode={mode}")


def load_records(set_name: str, limit: int | None) -> list[dict]:
    path = SETS[set_name]
    if not path.exists():
        raise SystemExit(f"{path} not found")
    recs = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    return recs[:limit] if limit else recs


def ft_model_path() -> str:
    if not RUNS.exists():
        raise SystemExit("train/runs.json not found: train a model first (python -m stitchproof.train.sft)")
    runs = json.loads(RUNS.read_text())
    return runs["final"]["sampler_path"]


# ---------------------------------------------------------------------------
# Direct-check answers -> flagged lines
# ---------------------------------------------------------------------------

_NUM = re.compile(r"\d+")


def _line_numbers(line: dict) -> set[int]:
    g = line["gold"]
    if g.get("range_start") is not None and g.get("range_end") is not None:
        return set(range(g["range_start"], g["range_end"] + 1))
    label = g.get("label") or ""
    m = _NUM.search(label)
    return {int(m.group())} if m else set()


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def map_flag(record: dict, row: str, taken: set[int]) -> int | None:
    lines = record["lines"]
    counted = [i for i, l in enumerate(lines) if l["gold"]["kind"] in ("row", "round", "foundation", "unsupported")]
    nr = _norm(row)
    for i in counted:  # exact label match
        lab = lines[i]["gold"].get("label")
        if lab and _norm(lab) == nr and i not in taken:
            return i
    nums = [int(x) for x in _NUM.findall(row)]
    if not nums:
        if "ch" in row.lower() or "foundation" in row.lower():
            return next((i for i in counted if lines[i]["gold"]["kind"] == "foundation"), None)
        return None
    n = nums[0]
    matches = [i for i in counted if n in _line_numbers(lines[i])]
    free = [i for i in matches if i not in taken]
    return (free or matches or [None])[0]


def parse_direct(text: str) -> list[str] | None:
    cleaned = strip_thinking(text or "")
    decoder = json.JSONDecoder()
    i = cleaned.find("{")
    while i != -1:
        try:
            obj, _ = decoder.raw_decode(cleaned, i)
            if isinstance(obj, dict) and isinstance(obj.get("errors"), list):
                rows = []
                for e in obj["errors"]:
                    if isinstance(e, dict) and e.get("row") is not None:
                        rows.append(str(e["row"]))
                    elif isinstance(e, (str, int)):
                        rows.append(str(e))
                return rows
        except json.JSONDecodeError:
            pass
        i = cleaned.find("{", i + 1)
    return None


# ---------------------------------------------------------------------------


def build_batch(records: list[dict], mode: str) -> list[list[dict]]:
    if mode == "direct":
        return [direct_messages(r["text"]) for r in records]
    return [messages_for_line(r["header"], l["prev"], l["text"]) for r in records for l in r["lines"]]


async def run(args) -> dict:
    model_kind, mode = (APPROACHES[args.approach] if args.approach else (args.model, args.mode))
    approach = args.approach or approach_for(model_kind, mode)
    records = load_records(args.set, args.limit)
    private = args.set == "real"

    model = TEACHER_MODEL if model_kind == "teacher" else BASE_MODEL
    model_path = ft_model_path() if model_kind == "ft" else (args.model_path or None)
    max_tokens = 2048 if mode == "direct" else 400
    batch = build_batch(records, mode)

    p_tok, c_tok = estimate_tokens(model, batch, max_tokens if mode == "direct" else 150)
    pp, cp = PRICES.get(model, (0.5, 1.5))
    est = p_tok / 1e6 * pp + c_tok / 1e6 * cp
    print(f"[{approach}/{args.set}] {len(records)} patterns, {len(batch)} requests to {model}{' (' + model_path + ')' if model_path else ''}")
    print(f"  estimate: {p_tok:,} prompt tokens + up to {c_tok:,} completion tokens = about US${est:.2f} at the PRICES table")
    if est > args.max_usd:
        raise SystemExit(f"  estimate exceeds --max-usd {args.max_usd}; stopping")

    sampler = Sampler(model=model, model_path=model_path, max_tokens=max_tokens, concurrency=args.concurrency)
    outputs = await sampler.complete_many(batch)
    print(f"  usage: {sampler.usage}")

    preds: dict[str, PatternPrediction] = {}
    saved = []
    k = 0
    for rec in records:
        if mode == "direct":
            raw = outputs[k]
            k += 1
            rows = parse_direct(raw)
            flagged: set[int] = set()
            for row in rows or []:
                i = map_flag(rec, row, flagged)
                if i is not None:
                    flagged.add(i)
            preds[rec["id"]] = PatternPrediction(rec["id"], flagged, valid=rows is not None)
            saved.append({"id": rec["id"], "flagged": sorted(flagged), "valid": rows is not None, **({} if private else {"raw": raw})})
        else:
            raws = outputs[k : k + len(rec["lines"])]
            k += len(rec["lines"])
            parsed = [parse_model_output(r) for r in raws]
            programs = [p.program for p in parsed]
            res = simulate(programs)
            flagged = {r.index for r in res if r.status == Status.ERROR}
            statuses = [r.status.value for r in res]
            preds[rec["id"]] = PatternPrediction(rec["id"], flagged, statuses=statuses, programs=programs)
            item = {"id": rec["id"], "flagged": sorted(flagged), "statuses": statuses}
            if not private:
                item["raw"] = raws
                item["explanations"] = [r.explanation for r in res]
            saved.append(item)

    m = score(records, preds, mode)
    result = {
        "approach": approach,
        "model": model,
        "model_path": model_path,
        "set": args.set,
        "mode": mode,
        "n_patterns": len(records),
        "usage": sampler.usage.__dict__,
        "metrics": m.to_dict(),
        "predictions": saved,
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / f"{approach}_{args.set}.json"
    out.write_text(json.dumps(result, indent=1))
    print(f"  errors caught {m.errors_caught} | false alarms {m.false_alarms} | pattern accuracy {m.pattern_accuracy} | valid JSON {m.valid_json}")
    if mode == "parse":
        print(f"  line exact {m.line_exact} | count-equivalent {m.count_equiv} | stated faithful {m.stated_faithful}")
    print(f"  saved {out}")
    return result


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--approach", choices=list(APPROACHES))
    ap.add_argument("--model", choices=["base", "ft", "teacher"])
    ap.add_argument("--mode", choices=["parse", "direct"])
    ap.add_argument("--model-path", default=None, help="override sampler checkpoint (tinker://...)")
    ap.add_argument("--set", choices=list(SETS), required=True)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--concurrency", type=int, default=32)
    ap.add_argument("--max-usd", type=float, default=5.0)
    args = ap.parse_args(argv)
    if not args.approach and not (args.model and args.mode):
        ap.error("give --approach, or both --model and --mode")
    asyncio.run(run(args))


if __name__ == "__main__":
    main(sys.argv[1:])
