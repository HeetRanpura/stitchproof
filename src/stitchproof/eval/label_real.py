"""Label a real (permitted) draft pattern line by line, for the private real-pattern eval set.

    python -m stitchproof.eval.label_real data/real/<draft>.txt

For each line it shows the local model's parse and the simulator's verdict, and you accept,
correct or reclassify it. The gold programs are appended to data/real/real_labelled.jsonl,
which `python -m stitchproof.eval.run_eval --set real ...` reads.

Privacy: input and output must live under data/real/ (gitignored). The tool refuses to run in CI
or without an interactive terminal, writes nothing else, and never logs pattern text. The model
runs locally (llama.cpp by default; STITCHPROOF_BACKEND to change).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

from ..schema import LineKind, LineProgram, to_compact_json
from ..segment import segment
from ..simulate import simulate

REAL_DIR = Path("data/real")
OUT = REAL_DIR / "real_labelled.jsonl"

HELP = """[a]ccept  [e]dit JSON  [n]ote  [u]nsupported  [b]ack  [s]kip pattern  [q]uit (progress kept)"""


def _inside_real(path: Path) -> bool:
    try:
        path.resolve().relative_to(REAL_DIR.resolve())
        return True
    except ValueError:
        return False


def guard(path: Path) -> None:
    if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
        raise SystemExit("label_real never runs in CI.")
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise SystemExit("label_real needs an interactive terminal (no pipes or logs).")
    if not _inside_real(path):
        raise SystemExit(f"Real drafts must live under {REAL_DIR}/ (gitignored).")


def pattern_id(text: str) -> str:
    """A content hash, so no title or designer name ends up in the id."""
    return "real-" + hashlib.sha256(text.encode()).hexdigest()[:12]


def _ask_json(current: LineProgram) -> LineProgram | None:
    print("Paste the corrected program JSON on one line (empty to cancel):")
    raw = input("> ").strip()
    if not raw:
        return None
    try:
        return LineProgram.model_validate_json(raw)
    except Exception as e:  # noqa: BLE001
        print(f"Not a valid program: {str(e).splitlines()[0]}")
        return None


def label(path: Path) -> None:
    from ..app.local_model import LineParser, get_backend

    text = path.read_text(errors="replace")
    pid = pattern_id(text)
    done = set()
    if OUT.exists():
        done = {json.loads(l)["id"] for l in OUT.read_text().splitlines() if l.strip()}
    if pid in done:
        raise SystemExit(f"{path.name} is already labelled ({pid}).")
    progress = REAL_DIR / f".progress_{pid}.json"
    seg = segment(text, merge_wrapped=path.suffix.lower() == ".pdf")
    parser = LineParser(get_backend())
    parses = parser.parse([(seg.header, l.prev_text, l.text) for l in seg.lines])
    gold: list[LineProgram | None] = [p.program for p in parses]
    accepted: dict[int, dict] = json.loads(progress.read_text()) if progress.exists() else {}
    for k, v in accepted.items():
        gold[int(k)] = LineProgram.model_validate(v)

    i = min((j for j in range(len(seg.lines)) if str(j) not in accepted), default=len(seg.lines))
    print(HELP)
    while i < len(seg.lines):
        line = seg.lines[i]
        prog = gold[i]
        verdict = simulate(gold[: i + 1])[i] if all(g is not None for g in gold[: i + 1]) else None
        print(f"\n[{i + 1}/{len(seg.lines)}] {line.text}")
        print(f"  model: {to_compact_json(prog) if prog else '(unreadable)'}")
        if verdict:
            print(f"  -> {verdict.status.value}: {verdict.explanation}")
        choice = input("  [a/e/n/u/b/s/q] > ").strip().lower() or "a"
        if choice == "q":
            progress.write_text(json.dumps(accepted))
            print("Progress saved.")
            return
        if choice == "s":
            progress.unlink(missing_ok=True)
            print("Skipped; nothing saved for this pattern.")
            return
        if choice == "b":
            i = max(0, i - 1)
            accepted.pop(str(i), None)
            continue
        if choice == "n":
            prog = LineProgram(kind=LineKind.NOTE)
        elif choice == "u":
            reason = input("  reason > ").strip() or "unsupported construction"
            stated = input("  stated count (blank if none) > ").strip()
            prog = LineProgram(kind=LineKind.UNSUPPORTED, unsupported_reason=reason, stated_count=int(stated) if stated.isdigit() else None)
        elif choice == "e":
            edited = _ask_json(prog or LineProgram(kind=LineKind.NOTE))
            if edited is None:
                continue
            prog = edited
        elif prog is None:
            print("  The model output is unreadable: edit it (e), or mark it note (n) or unsupported (u).")
            continue
        gold[i] = prog
        accepted[str(i)] = json.loads(prog.model_dump_json())
        progress.write_text(json.dumps(accepted))
        i += 1

    from ..generate.build_dataset import pattern_record

    rec = pattern_record(pid, "real", "real", None, [l.text for l in seg.lines], gold, [], [], source="real draft (permitted)")
    with OUT.open("a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    progress.unlink(missing_ok=True)
    print(f"\nSaved {pid}: {len(seg.lines)} lines, {len(rec['error_lines'])} lines with count errors, to {OUT}.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("draft", type=Path)
    args = ap.parse_args()
    guard(args.draft)
    label(args.draft)


if __name__ == "__main__":
    main()
