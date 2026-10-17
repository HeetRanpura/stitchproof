"""Write eval/results/summary.md from the per-approach result files.

    python -m stitchproof.eval.report
"""
from __future__ import annotations

import json
from pathlib import Path

RESULTS = Path("eval/results")
SET_FILES = {
    "pilot": Path("data/generated/pilot.jsonl"),
    "synth": Path("data/generated/eval_synth.jsonl"),
    "ood": Path("data/ood/ood.jsonl"),
}
NAMES = {
    "A": "A: base, direct check",
    "B": "B: teacher, direct check (reference)",
    "C": "C: base + simulator",
    "D": "D: fine-tuned + simulator",
}
SET_TITLES = {"pilot": "Pilot (40 template patterns)", "synth": "eval_synth (held-out styles and shapes)", "ood": "OOD (written by a different model family)", "real": "Real drafts"}

ROWS = [
    ("errors_caught", "**Errors caught**"),
    ("false_alarms", "**False alarms**"),
    ("pattern_accuracy", "Pattern-level accuracy"),
    ("valid_json", "Valid JSON"),
    ("line_exact", "Line parse exact match"),
    ("count_equiv", "Count-equivalence"),
    ("stated_faithful", "Stated-count faithfulness"),
    ("missing_stated_warned", "Missing count warned"),
]


def fmt(r: dict | None) -> str:
    if not r or not r["den"]:
        return "–"
    return f"{100 * r['num'] / r['den']:.1f}% ({r['num']}/{r['den']})"


def load() -> dict[str, dict[str, dict]]:
    out: dict[str, dict[str, dict]] = {}
    for f in sorted(RESULTS.glob("[ABCD]_*.json")):
        d = json.loads(f.read_text())
        out.setdefault(d["set"], {})[d["approach"]] = d
    return out


def table(results: dict[str, dict]) -> str:
    aps = sorted(results)
    lines = ["| Metric | " + " | ".join(NAMES[a] for a in aps) + " |", "| --- |" + " --- |" * len(aps)]
    for key, title in ROWS:
        vals = []
        for a in aps:
            m = results[a]["metrics"]
            if results[a]["mode"] == "direct" and key in ("line_exact", "count_equiv", "stated_faithful", "missing_stated_warned"):
                vals.append("n/a")
            else:
                vals.append(fmt(m.get(key)))
        lines.append(f"| {title} | " + " | ".join(vals) + " |")
    lines.append("| Flags on non-row lines | " + " | ".join(str(results[a]["metrics"]["flags_on_non_rows"]) for a in aps) + " |")
    lines.append(
        "| Can't check (correct / wrong) | "
        + " | ".join(
            "n/a" if results[a]["mode"] == "direct" else f"{results[a]['metrics']['cant_check_correct']} / {results[a]['metrics']['cant_check_wrong']}"
            for a in aps
        )
        + " |"
    )
    return "\n".join(lines)


def confusion(results: dict[str, dict]) -> str:
    aps = sorted(results)
    types = sorted({t for a in aps for t in results[a]["metrics"]["by_error_type"]})
    lines = ["| Seeded error type | " + " | ".join(a for a in aps) + " |", "| --- |" + " --- |" * len(aps)]
    for t in types:
        lines.append(f"| {t} | " + " | ".join(fmt(results[a]["metrics"]["by_error_type"].get(t)) for a in aps) + " |")
    return "\n".join(lines)


def _more_times(t: str) -> bool:
    return "more time" in t


def _other_heldout(t: str) -> bool:
    dash = t.startswith(("Round ", "Rounds ", "Row ", "Rows ")) and " - " in t[:16]
    return not _more_times(t) and (dash or "should have" in t.lower() or "each of the next" in t)


STYLE_GROUPS = [
    ("rep from * N more times", _more_times),
    ("other held-out styles only (dash labels, 'you should have N', 'each of the next N st')", _other_heldout),
    ("no held-out style (notes, foundation chains, ...)", lambda t: not _more_times(t) and not _other_heldout(t)),
]


def by_style(set_name: str, results: dict[str, dict]) -> str:
    """Line exact match (C, D) and false alarms split by held-out notation style."""
    from ..canonical import programs_equal
    from ..parse_output import parse_model_output
    from ..schema import LineProgram

    aps = [a for a in sorted(results) if results[a]["mode"] == "parse" and "raw" in results[a]["predictions"][0]]
    if not aps or set_name not in SET_FILES:
        return ""
    recs = {json.loads(l)["id"]: json.loads(l) for l in SET_FILES[set_name].read_text().splitlines() if l.strip()}
    lines = ["| Lines written in this style | " + " | ".join(f"{a}: exact match" for a in aps) + " | " + " | ".join(f"{a}: false alarms" for a in aps) + " |", "| --- |" + " --- |" * (2 * len(aps))]
    for name, match in STYLE_GROUPS:
        exact, fa = [], []
        for a in aps:
            e = [0, 0]
            f = [0, 0]
            for pred in results[a]["predictions"]:
                rec = recs[pred["id"]]
                err = set(rec["error_lines"])
                for i, (raw, line) in enumerate(zip(pred["raw"], rec["lines"])):
                    if not match(line["text"]):
                        continue
                    e[1] += 1
                    e[0] += programs_equal(parse_model_output(raw).program, LineProgram.model_validate(line["gold"]))
                    if line["gold"]["kind"] in ("row", "round", "foundation") and i not in err:
                        f[1] += 1
                        f[0] += i in pred["flagged"]
            exact.append(fmt({"num": e[0], "den": e[1]}))
            fa.append(fmt({"num": f[0], "den": f[1]}))
        lines.append(f"| {name} | " + " | ".join(exact) + " | " + " | ".join(fa) + " |")
    return "\n".join(lines)


def disagreements(set_name: str, results: dict[str, dict], n: int = 5) -> str:
    if "C" not in results or "D" not in results or set_name not in SET_FILES:
        return ""
    recs = {json.loads(l)["id"]: json.loads(l) for l in SET_FILES[set_name].read_text().splitlines() if l.strip()}
    c = {p["id"]: p for p in results["C"]["predictions"]}
    d = {p["id"]: p for p in results["D"]["predictions"]}
    rows = []
    for pid, rec in recs.items():
        if pid not in c or pid not in d:
            continue
        for i, line in enumerate(rec["lines"]):
            cs, ds = c[pid]["statuses"][i], d[pid]["statuses"][i]
            if cs != ds:
                rows.append((pid, line["text"], line["truth"], cs, ds, c[pid]["explanations"][i], d[pid]["explanations"][i]))
    rows.sort(key=lambda r: (r[4] != r[2], r[0]))  # D-correct cases first
    if not rows:
        return "C and D never disagree on a line status in this set."
    out = [f"{len(rows)} lines where C and D give different statuses. First {min(n, len(rows))}:", ""]
    for pid, text, truth, cs, ds, ce, de in rows[:n]:
        out += [f"- `{pid}`: `{text}`", f"  - truth **{truth}** · C **{cs}**: {ce}", f"  - D **{ds}**: {de}"]
    return "\n".join(out)


def headline_chart(allres: dict[str, dict[str, dict]], path: Path) -> bool:
    """Errors caught vs false alarms per approach, one panel per set (same % axis)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    sets = [s for s in ("synth", "ood") if s in allres]
    if not sets:
        return False
    surface, ink, ink2, grid = "#fcfcfb", "#0b0b0b", "#52514e", "#e1e0d9"
    caught_c, fa_c = "#2a78d6", "#eb6834"  # categorical slots 1 and 2
    fig, axes = plt.subplots(1, len(sets), figsize=(5.2 * len(sets), 3.8), dpi=150, sharey=True)
    fig.patch.set_facecolor(surface)
    axes = [axes] if len(sets) == 1 else list(axes)
    for ax, set_name in zip(axes, sets):
        res = allres[set_name]
        aps = sorted(res)
        x = range(len(aps))
        w = 0.36
        for off, key, color, name in ((-w / 2 - 0.01, "errors_caught", caught_c, "Errors caught"), (w / 2 + 0.01, "false_alarms", fa_c, "False alarms")):
            vals = [res[a]["metrics"][key] for a in aps]
            pct = [100 * v["num"] / v["den"] if v["den"] else 0 for v in vals]
            ax.bar([i + off for i in x], pct, width=w, color=color, label=name, edgecolor=surface, linewidth=1.5)
            for i, (pc, v) in enumerate(zip(pct, vals)):
                ax.annotate(f"{pc:.0f}%\n{v['num']}/{v['den']}", (i + off, pc), xytext=(0, 2), textcoords="offset points", ha="center", va="bottom", fontsize=6.5, color=ink2)
        ax.set_xticks(list(x))
        ax.set_xticklabels([{"A": "A\nbase, direct", "B": "B\nteacher, direct*", "C": "C\nbase + sim", "D": "D\nfine-tuned + sim"}[a] for a in aps], fontsize=8, color=ink2)
        ax.set_title(SET_TITLES[set_name], fontsize=9, color=ink, loc="left")
        ax.set_facecolor(surface)
        ax.set_ylim(0, 118)
        ax.grid(axis="y", color=grid, linewidth=0.6)
        ax.set_axisbelow(True)
        for sp in ("top", "right", "left"):
            ax.spines[sp].set_visible(False)
        ax.spines["bottom"].set_color(grid)
        ax.tick_params(axis="y", colors=ink2, labelsize=8)
    axes[0].set_ylabel("% of rows", color=ink2, fontsize=9)
    axes[0].legend(frameon=False, fontsize=8, loc="upper left", labelcolor=ink)
    note = "*B: a much larger model, reference only" + (", run on 15 patterns" if "B" in allres.get("synth", {}) and allres["synth"]["B"]["n_patterns"] < 60 else "")
    fig.text(0.01, 0.01, note, fontsize=7, color=ink2)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(path, facecolor=surface)
    plt.close(fig)
    return True


def main() -> None:
    allres = load()
    parts = [
        "# StitchProof evaluation summary",
        "",
        "Generated by `python -m stitchproof.eval.report` from the files in `eval/results/`. Every rate is shown with its count.",
        "Errors caught = seeded error rows flagged ERROR / all seeded error rows. False alarms = clean rows flagged ERROR / all clean rows.",
        "B uses a much larger teacher model and is a reference only.",
        "",
    ]
    if headline_chart(allres, RESULTS / "headline.png"):
        parts += ["![Errors caught and false alarms per approach](headline.png)", ""]
    for set_name in ("synth", "ood", "pilot", "real"):
        if set_name not in allres:
            continue
        res = allres[set_name]
        parts += [f"## {SET_TITLES[set_name]}", "", table(res), "", "### Errors caught by seeded error type", "", confusion(res), ""]
        st = by_style(set_name, res) if set_name == "synth" else ""
        if st:
            parts += ["### By held-out notation style", "", "Every eval_synth pattern uses all four notation styles that never appear in training. Lines are grouped so each line counts once.", "", st, ""]
        dis = disagreements(set_name, res)
        if dis:
            parts += ["### Where C and D disagree", "", dis, ""]
        usage = ", ".join(f"{a}: {r['usage']['prompt_tokens']:,} prompt + {r['usage']['completion_tokens']:,} completion tokens" for a, r in sorted(res.items()))
        parts += [f"Token usage: {usage}.", ""]
    (RESULTS / "summary.md").write_text("\n".join(parts))
    print(f"wrote {RESULTS / 'summary.md'}")


if __name__ == "__main__":
    main()
