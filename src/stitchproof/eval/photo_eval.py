"""Does the Gemma 4 photo reader actually work? Measure it on rendered synthetic patterns.

    ollama pull gemma4:e4b-it-qat
    llama-server -m models/stitchproof-base-q4_k_m.gguf --lora models/stitchproof-lora-v1.gguf --port 8080 --jinja
    python -m stitchproof.eval.photo_eval --n 12

Each pattern (from eval_synth, held-out styles) is rendered twice: a clean "scan" and a
"photo" (slight rotation, uneven lighting, noise, JPEG). Gemma transcribes each image; we report
line and number fidelity, then run the full local StitchProof pipeline on the transcription and
compare errors caught / false alarms with running it on the original text.
Everything runs locally; no Tinker calls.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import time
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from ..app import photo_reader
from ..app.local_model import LineParser, LlamaServerBackend, check_pattern
from ..simulate import Status

EVAL = Path("data/generated/eval_synth.jsonl")
OUT_JSON = Path("eval/results/photo_reader.json")
OUT_MD = Path("eval/results/photo_reader.md")
SAMPLES = Path("docs/screenshots")
_NUM = re.compile(r"\d+")


def _font(serif: bool, size: int):
    from matplotlib import font_manager

    path = font_manager.findfont("DejaVu Serif" if serif else "DejaVu Sans")
    return ImageFont.truetype(path, size)


def render_scan(text: str, serif: bool) -> Image.Image:
    font = _font(serif, 26)
    lines = text.splitlines()
    width = max(int(font.getlength(l)) for l in lines) + 120
    height = 60 + 40 * len(lines) + 40
    img = Image.new("RGB", (width, height), "white")
    d = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        d.text((60, 50 + 40 * i), line, fill=(20, 20, 20), font=font)
    return img


def make_photo(scan: Image.Image, rng: random.Random) -> Image.Image:
    img = scan.rotate(rng.uniform(-2.0, 2.0), resample=Image.BICUBIC, expand=True, fillcolor=(238, 234, 226))
    w, h = img.size
    # uneven lighting: a soft horizontal gradient
    shade = Image.linear_gradient("L").rotate(90).resize((w, h))
    img = Image.composite(img, Image.new("RGB", (w, h), (205, 198, 186)), shade.point(lambda v: 150 + v * 105 // 255))
    noise = Image.effect_noise((w, h), 18).convert("RGB")
    img = Image.blend(img, noise, 0.08).filter(ImageFilter.GaussianBlur(0.6))
    return img


def _norm(line: str) -> str:
    return " ".join(line.split()).strip()


def fidelity(original: str, transcribed: str) -> dict:
    a = [_norm(l) for l in original.splitlines() if l.strip()]
    b = [_norm(l) for l in transcribed.splitlines() if l.strip()]
    sm = SequenceMatcher(None, a, b, autojunk=False)
    exact = sum(block.size for block in sm.get_matching_blocks())
    na, nb = Counter(_NUM.findall(original)), Counter(_NUM.findall(transcribed))
    kept = sum((na & nb).values())
    return {
        "lines": len(a),
        "lines_exact": exact,
        "numbers": sum(na.values()),
        "numbers_kept": kept,
        "numbers_extra": sum((nb - na).values()),
        "char_similarity": round(SequenceMatcher(None, "\n".join(a), "\n".join(b), autojunk=False).ratio(), 4),
    }


def _label_key(label: str | None) -> str | None:
    if not label:
        return None
    nums = _NUM.findall(label)
    return "-".join(nums) if nums else None


def flags_vs_truth(rec: dict, check) -> dict:
    """Map flagged lines to gold rows by row number (transcription may change line positions)."""
    gold = {}
    for i, line in enumerate(rec["lines"]):
        k = _label_key(line["gold"].get("label")) if line["gold"]["kind"] in ("row", "round") else None
        if k:
            gold.setdefault(k, i in rec["error_lines"])
    flagged = {_label_key(r.label) for r in check.results if r.status == Status.ERROR}
    flagged.discard(None)
    err = [k for k, e in gold.items() if e]
    clean = [k for k, e in gold.items() if not e]
    return {
        "error_rows": len(err),
        "caught": sum(k in flagged for k in err),
        "clean_rows": len(clean),
        "false_alarms": sum(k in flagged for k in clean),
    }


def pct(a: int, b: int) -> str:
    return f"{100 * a / b:.1f}% ({a}/{b})" if b else "n/a (0/0)"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=12)
    args = ap.parse_args()
    ok, why = photo_reader.status()
    if not ok:
        raise SystemExit(f"Gemma not available: {why}")
    recs = [json.loads(l) for l in EVAL.read_text().splitlines() if l.strip()]
    rng = random.Random(7)
    with_err = [r for r in recs if r["error_lines"]]
    clean = [r for r in recs if not r["error_lines"]]
    picked = rng.sample(with_err, min(len(with_err), (args.n * 2) // 3)) + rng.sample(clean, args.n - (args.n * 2) // 3)
    parser = LineParser(LlamaServerBackend())
    rows = []
    SAMPLES.mkdir(parents=True, exist_ok=True)
    tmp = Path(".stitchproof_cache/photo_eval")
    tmp.mkdir(parents=True, exist_ok=True)
    for k, rec in enumerate(picked):
        scan = render_scan(rec["text"], serif=k % 2 == 1)
        photo = make_photo(scan, rng)
        base = check_pattern(rec["text"], parser)
        row = {"id": rec["id"], "shape": rec["shape"], "text_pipeline": flags_vs_truth(rec, base)}
        for variant, img in (("scan", scan), ("photo", photo)):
            path = tmp / f"{rec['id']}_{variant}.jpg"
            img.save(path, quality=92 if variant == "scan" else 70)
            if k == 0:
                img.save(SAMPLES / f"photo_reader_{variant}_example.jpg", quality=85)
            t = time.time()
            transcribed = photo_reader.transcribe(path)
            secs = time.time() - t
            chk = check_pattern(transcribed, parser, merge_wrapped=True)
            row[variant] = {"seconds": round(secs, 1), **fidelity(rec["text"], transcribed), **flags_vs_truth(rec, chk)}
            if k == 0:
                row[variant]["transcription"] = transcribed
        rows.append(row)
        print(f"{k + 1}/{len(picked)} {rec['id']}: scan lines {row['scan']['lines_exact']}/{row['scan']['lines']}, photo lines {row['photo']['lines_exact']}/{row['photo']['lines']}")

    def total(variant: str, key: str) -> int:
        return sum(r[variant][key] for r in rows)

    summary = {}
    for v in ("text_pipeline", "scan", "photo"):
        s = {"caught": total(v, "caught"), "error_rows": total(v, "error_rows"), "false_alarms": total(v, "false_alarms"), "clean_rows": total(v, "clean_rows")}
        if v != "text_pipeline":
            s |= {k: total(v, k) for k in ("lines", "lines_exact", "numbers", "numbers_kept", "numbers_extra")}
            s["seconds_mean"] = round(sum(r[v]["seconds"] for r in rows) / len(rows), 1)
            s["char_similarity_mean"] = round(sum(r[v]["char_similarity"] for r in rows) / len(rows), 4)
        summary[v] = s
    OUT_JSON.write_text(json.dumps({"model": photo_reader.model_name(), "n_patterns": len(rows), "summary": summary, "patterns": rows}, indent=1))

    S = summary
    md = [
        "# Gemma 4 photo reader",
        "",
        f"Model: `{photo_reader.model_name()}` via Ollama, on this Mac. {len(rows)} held-out eval_synth patterns ({sum(1 for r in picked if r['error_lines'])} with seeded errors), each rendered as a clean scan and as a photo-like image (rotation, uneven light, noise, JPEG). Rows are matched by row number.",
        "",
        "| | Original text | Scan → Gemma | Photo → Gemma |",
        "| --- | --- | --- | --- |",
        f"| Lines transcribed exactly | – | {pct(S['scan']['lines_exact'], S['scan']['lines'])} | {pct(S['photo']['lines_exact'], S['photo']['lines'])} |",
        f"| Numbers kept | – | {pct(S['scan']['numbers_kept'], S['scan']['numbers'])} | {pct(S['photo']['numbers_kept'], S['photo']['numbers'])} |",
        f"| Extra numbers introduced | – | {S['scan']['numbers_extra']} | {S['photo']['numbers_extra']} |",
        f"| Character similarity (mean) | – | {S['scan']['char_similarity_mean']} | {S['photo']['char_similarity_mean']} |",
        f"| **Errors caught (end to end)** | {pct(S['text_pipeline']['caught'], S['text_pipeline']['error_rows'])} | {pct(S['scan']['caught'], S['scan']['error_rows'])} | {pct(S['photo']['caught'], S['photo']['error_rows'])} |",
        f"| **False alarms (end to end)** | {pct(S['text_pipeline']['false_alarms'], S['text_pipeline']['clean_rows'])} | {pct(S['scan']['false_alarms'], S['scan']['clean_rows'])} | {pct(S['photo']['false_alarms'], S['photo']['clean_rows'])} |",
        f"| Seconds per image (mean) | – | {S['scan']['seconds_mean']} | {S['photo']['seconds_mean']} |",
        "",
        "Example images: `docs/screenshots/photo_reader_scan_example.jpg`, `docs/screenshots/photo_reader_photo_example.jpg`.",
    ]
    OUT_MD.write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
