"""Results table rows, the silhouette chart, and Markdown/HTML reports."""
from __future__ import annotations

import base64
import io
from datetime import date

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from jinja2 import Environment  # noqa: E402

from ..simulate import Status  # noqa: E402
from .local_model import PatternCheck  # noqa: E402

FOOTER = "Runs on your computer. Your pattern never leaves it. StitchProof checks stitch math only, not gauge, sizing or shape."

ICON = {"OK": "✔ OK", "ERROR": "✖ ERROR", "WARNING": "⚠ WARNING", "CAN'T CHECK": "? CAN'T CHECK", "NOTE": "· note"}

# Chart tokens (reference palette): one hue for rows, the reserved critical red for errors.
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e1e0d9"
BAR = "#2a78d6"
CRITICAL = "#d03b3b"
MUTED = "#b5b3ab"

_CLS = {"✔ OK": "OK", "✖ ERROR": "ERROR", "⚠ WARNING": "WARNING", "? CAN'T CHECK": "CANT", "· note": "CANT"}

COLUMNS = ["#", "Row", "Text", "Parsed program", "Available", "Used", "Made", "Stated", "Status", "Explanation"]


def _n(v):
    return "" if v is None else v


def table_rows(check: PatternCheck, include_notes: bool = False) -> list[list]:
    rows = []
    for i, (text, r) in enumerate(zip(check.lines, check.results)):
        if r.status == Status.NOTE and not include_notes:
            continue
        rows.append([i + 1, r.label or "", text, r.program_text, _n(r.available), _n(r.used), _n(r.made), _n(r.stated), ICON[r.status.value], r.explanation])
    return rows


def summary_line(check: PatternCheck) -> str:
    c = check.counts
    rows = sum(v for k, v in c.items() if k != "NOTE")
    parts = [f"{rows} rows checked"]
    for k, one, many in (("ERROR", "error", "errors"), ("WARNING", "warning", "warnings"), ("CAN'T CHECK", "can't check", "can't check")):
        if c.get(k):
            parts.append(f"{c[k]} {one if c[k] == 1 else many}")
    if not c.get("ERROR"):
        parts.append("no stitch-count errors found")
    return ", ".join(parts) + "."


def silhouette(check: PatternCheck):
    """Bar per counted row: stitches made. For amigurumi this is the outline of the piece."""
    xs, ys, labels, kinds = [], [], [], []
    for r in check.results:
        if r.status == Status.NOTE or r.kind == "foundation":
            continue
        rows = r.rows or [None]
        for k, row in enumerate(rows):
            made = row.made if row is not None else r.stated
            xs.append(len(xs))
            ys.append(made if made is not None else 0)
            base = r.label or f"line {r.index + 1}"
            labels.append(base if len(rows) == 1 else f"{base} ({k + 1})")
            kinds.append("ERROR" if r.status == Status.ERROR else ("CANT" if r.status == Status.CANT_CHECK else "OK"))
    fig, ax = plt.subplots(figsize=(max(6, 0.32 * len(xs) + 2), 3.4), dpi=110)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    if not xs:
        ax.text(0.5, 0.5, "No rows to chart", ha="center", va="center", color=INK_2, transform=ax.transAxes)
        ax.axis("off")
        return fig
    colors = [CRITICAL if k == "ERROR" else (MUTED if k == "CANT" else BAR) for k in kinds]
    hatches = ["////" if k in ("ERROR", "CANT") else "" for k in kinds]
    bars = ax.bar(xs, ys, color=colors, width=0.78, edgecolor=SURFACE, linewidth=1.5)
    for b, h in zip(bars, hatches):
        if h:
            b.set_hatch(h)
    for x, y, k in zip(xs, ys, kinds):
        if k == "ERROR":
            ax.annotate("ERROR", (x, y), xytext=(0, 4), textcoords="offset points", ha="center", fontsize=7, fontweight="bold", color=INK)
        elif k == "CANT":
            ax.annotate("?", (x, y), xytext=(0, 3), textcoords="offset points", ha="center", fontsize=8, color=INK_2)
    ax.set_ylabel("Stitches made", color=INK_2, fontsize=9)
    ax.set_title("Stitch counts row by row", color=INK, fontsize=10, loc="left")
    step = max(1, len(xs) // 24)
    ax.set_xticks(xs[::step])
    ax.set_xticklabels(labels[::step], rotation=60, ha="right", fontsize=7, color=INK_2)
    ax.tick_params(axis="y", colors=INK_2, labelsize=8)
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.set_ylim(0, max(ys) * 1.15 + 1)
    fig.tight_layout()
    return fig


def chart_png(check: PatternCheck) -> bytes:
    fig = silhouette(check)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=SURFACE)
    plt.close(fig)
    return buf.getvalue()


def to_markdown(check: PatternCheck, title: str = "StitchProof report", chart_file: str | None = None) -> str:
    out = [f"# {title}", "", f"Checked {date.today().isoformat()} with {check.backend}.", "", f"**{summary_line(check)}**", ""]
    flagged = [(t, r) for t, r in zip(check.lines, check.results) if r.status in (Status.ERROR, Status.WARNING, Status.CANT_CHECK)]
    if flagged:
        out += ["## Rows to look at", ""]
        for t, r in flagged:
            out += [f"- **{ICON[r.status.value]}** `{t}`  ", f"  {r.explanation}"]
        out.append("")
    if chart_file:
        out += [f"![Stitch counts row by row]({chart_file})", ""]
    out += ["## All rows", "", "| " + " | ".join(COLUMNS) + " |", "|" + " --- |" * len(COLUMNS)]
    for row in table_rows(check):
        out.append("| " + " | ".join(str(c).replace("|", "\\|") for c in row) + " |")
    out += ["", f"_{FOOTER}_", ""]
    return "\n".join(out)


_HTML = Environment(autoescape=True).from_string(
    """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }}</title>
<style>
:root { --bg:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --line:#e1e0d9; --err:#d03b3b; --warn:#b26b00; --ok:#1f7a3a; --muted:#77756e; }
@media (prefers-color-scheme: dark) { :root { --bg:#1a1a19; --ink:#ffffff; --ink2:#c3c2b7; --line:#2c2c2a; --err:#e56060; --warn:#e3a33b; --ok:#5fbf7a; --muted:#a3a198; } }
body { background:var(--bg); color:var(--ink); font:15px/1.5 system-ui, -apple-system, sans-serif; margin:0 auto; max-width:1100px; padding:24px 16px; }
h1 { font-size:22px; margin:0 0 4px; } .meta { color:var(--ink2); margin:0 0 16px; }
.summary { font-weight:600; margin:12px 0 20px; }
.chart img { max-width:100%; height:auto; border:1px solid var(--line); border-radius:6px; background:#fcfcfb; }
table { border-collapse:collapse; width:100%; font-size:13px; } th, td { border-bottom:1px solid var(--line); padding:6px 8px; text-align:left; vertical-align:top; }
th { color:var(--ink2); font-weight:600; } td.num { text-align:right; font-variant-numeric:tabular-nums; }
.s-ERROR { color:var(--err); font-weight:700; } .s-WARNING { color:var(--warn); font-weight:600; } .s-OK { color:var(--ok); } .s-CANT { color:var(--muted); }
details { margin:6px 0; } summary { cursor:pointer; } code { font-size:13px; }
.wrap { overflow-x:auto; } footer { color:var(--ink2); margin-top:24px; font-size:13px; }
</style></head><body>
<h1>{{ title }}</h1>
<p class="meta">Checked {{ today }} with {{ backend }}.</p>
<p class="summary">{{ summary }}</p>
{% if flagged %}<h2>Rows to look at</h2>
{% for t, r in flagged %}<details open><summary><span class="s-{{ r.cls }}">{{ r.icon }}</span> <code>{{ t }}</code></summary><p>{{ r.explanation }}</p></details>{% endfor %}{% endif %}
<div class="chart"><img alt="Bar chart of stitches made per row; error rows are hatched red and labelled ERROR" src="data:image/png;base64,{{ png }}"></div>
<h2>All rows</h2>
<div class="wrap"><table><thead><tr>{% for c in columns %}<th>{{ c }}</th>{% endfor %}</tr></thead><tbody>
{% for row, cls in rows %}<tr>{% for c in row %}<td{% if loop.index in [5,6,7,8] %} class="num"{% endif %}{% if loop.index == 9 %} class="s-{{ cls }}"{% endif %}>{{ c }}</td>{% endfor %}</tr>
{% endfor %}</tbody></table></div>
<footer>{{ footer }}</footer>
</body></html>"""
)


def to_html(check: PatternCheck, title: str = "StitchProof report") -> str:
    flagged = []
    for t, r in zip(check.lines, check.results):
        if r.status in (Status.ERROR, Status.WARNING, Status.CANT_CHECK):
            cls = {"ERROR": "ERROR", "WARNING": "WARNING", "CAN'T CHECK": "CANT"}[r.status.value]
            flagged.append((t, {"cls": cls, "icon": ICON[r.status.value], "explanation": r.explanation}))
    return _HTML.render(
        title=title,
        today=date.today().isoformat(),
        backend=check.backend,
        summary=summary_line(check),
        flagged=flagged,
        png=base64.b64encode(chart_png(check)).decode(),
        columns=COLUMNS,
        rows=[(row, _CLS[row[8]]) for row in table_rows(check)],
        footer=FOOTER,
    )
