"""StitchProof local app.

    python -m stitchproof.app.ui                     # local model via llama.cpp server (default)
    STITCHPROOF_BACKEND=ollama python -m stitchproof.app.ui
    STITCHPROOF_BACKEND=replay python -m stitchproof.app.ui   # demo on the synthetic examples, no model

The app binds to 127.0.0.1 only and has no analytics.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

import gradio as gr  # noqa: E402

from . import photo_reader  # noqa: E402
from .local_model import LineParser, ReplayBackend, backend_status, check_pattern, check_row, get_backend  # noqa: E402
from .report_export import COLUMNS, FOOTER, ICON, silhouette, summary_line, table_rows, to_html, to_markdown  # noqa: E402

EXAMPLE = """Tiny Ball
US terms. Worked in continuous spiral rounds.
Rnd 1: 6 sc in MR (6)
Rnd 2: inc x6 (12)
Rnd 3: (sc, inc) x6 (18)
Rnd 4: (sc 2, inc) x6 (24)
Rnd 5: (sc 3, inc) x6 (31)
Rnds 6-9: sc around (30)
Begin stuffing.
Rnd 10: (sc 3, dec) x6 (24)
Rnd 11: (sc 2, dec) x5 (18)
Rnd 12: (sc, dec) x6 (12)
Rnd 13: dec x6 (6)
FO, leave a long tail."""


def replay_example() -> str:
    """A synthetic eval pattern with a seeded error, for replay demos."""
    import json

    for line in Path("data/generated/eval_synth.jsonl").read_text().splitlines():
        rec = json.loads(line)
        if rec["seeded_errors"] and rec["shape"] == "sphere":
            return rec["text"]
    return EXAMPLE


def read_upload(path: str | None) -> tuple[str, bool]:
    if not path:
        return "", False
    p = Path(path)
    if p.suffix.lower() in photo_reader.IMAGE_TYPES:
        try:
            text = photo_reader.transcribe(p)
        except photo_reader.PhotoReaderUnavailable as e:
            raise gr.Error(f"Reading photos needs Gemma 4 running locally in Ollama ({e}). Please paste the pattern text instead.")
        except OSError as e:
            raise gr.Error(f"Gemma couldn't read this photo ({type(e).__name__}). Please paste the pattern text instead.")
        if not text.strip():
            raise gr.Error("Gemma couldn't find any text in this photo. Please paste the pattern text instead.")
        return text, True
    if p.suffix.lower() == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(p))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
        if not text.strip():
            raise gr.Error("This PDF has no text layer (it may be a scan). Please paste the pattern text instead.")
        return text, True
    return p.read_text(errors="replace"), False


def _details_html(check) -> str:
    items = []
    for text, r in zip(check.lines, check.results):
        if r.status.value in ("ERROR", "WARNING", "CAN'T CHECK"):
            cls = {"ERROR": "sp-err", "WARNING": "sp-warn", "CAN'T CHECK": "sp-cant"}[r.status.value]
            items.append(
                f'<details class="sp-item {cls}" open><summary><b>{ICON[r.status.value]}</b> &nbsp;<code>{_esc(text)}</code></summary>'
                f"<p>{_esc(r.explanation)}</p></details>"
            )
    if not items:
        return '<p class="sp-ok"><b>✔ No stitch-count errors found.</b> Every checked row adds up.</p>'
    return "\n".join(items)


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


CSS = """
.sp-item { border-left: 4px solid var(--border-color-primary); padding: 4px 10px; margin: 6px 0; border-radius: 4px; }
.sp-err { border-left-color: #d03b3b; } .sp-warn { border-left-color: #b26b00; } .sp-cant { border-left-color: #8a8880; }
.sp-item summary { cursor: pointer; } .sp-item p { margin: 6px 0 2px; }
.sp-banner-cloud { background: #fdecea; color: #7a1c1c; padding: 8px 12px; border-radius: 6px; font-weight: 600; }
.sp-footer { color: var(--body-text-color-subdued); font-size: 13px; margin-top: 12px; }
"""


def build(backend_kind: str | None = None) -> gr.Blocks:
    backend = get_backend(backend_kind)
    parser = LineParser(backend)
    ok, status = backend_status(backend)
    example = EXAMPLE
    if isinstance(backend, ReplayBackend):
        example = replay_example()

    def run_check(text, upload):
        merge = False
        note = ""
        if upload:
            text, merge = read_upload(upload)
            if Path(upload).suffix.lower() in photo_reader.IMAGE_TYPES:
                note = (
                    f"\n\nTranscribed from your photo by {photo_reader.model_name()} on this computer. "
                    "The text box now holds the transcription: compare it with the photo, fix anything misread, and press Check again."
                )
        if not text or not text.strip():
            raise gr.Error("Paste a pattern or upload a .txt, .md, .pdf or photo.")
        try:
            check = check_pattern(text, parser, merge_wrapped=merge)
        except OSError as e:
            raise gr.Error(f"The model backend isn't reachable ({backend.name}). Start it and try again. ({type(e).__name__})")
        fig = silhouette(check)
        out_dir = Path(tempfile.mkdtemp(prefix="stitchproof_"))
        md_path, html_path = out_dir / "stitchproof_report.md", out_dir / "stitchproof_report.html"
        md_path.write_text(to_markdown(check))
        html_path.write_text(to_html(check))
        rows = [r[1:] for r in table_rows(check)]
        return f"### {summary_line(check)}{note}", _details_html(check), fig, rows, [str(md_path), str(html_path)], text, None

    def run_row(prev, row_text):
        prev_n = int(prev) if prev not in (None, "") else None
        try:
            answer, res = check_row(prev_n, row_text or "", parser)
        except OSError as e:
            raise gr.Error(f"The model backend isn't reachable ({backend.name}). ({type(e).__name__})")
        detail = "" if res is None else f"**{ICON[res.status.value]}** · {res.explanation}"
        return f"### {answer}", detail

    with gr.Blocks(title="StitchProof", analytics_enabled=False) as demo:
        gr.Markdown("# StitchProof\nA local tech editor for crochet patterns: the model reads each row, plain code checks every stitch count.")
        if not backend.is_local:
            gr.HTML(f'<div class="sp-banner-cloud">{_esc(backend.name)}. Your pattern is NOT private in this mode.</div>')
        vok, vstatus = photo_reader.status()
        gr.Markdown(
            f"Model: **{backend.name}** · {'ready' if ok else '⚠ ' + status}  \n"
            f"Photo reader: **{'Gemma 4, ' + vstatus if vok else 'off'}**{'' if vok else ' (' + vstatus + '; paste text instead)'}"
        )

        with gr.Tab("Check a pattern"):
            with gr.Row():
                with gr.Column(scale=3):
                    text = gr.Textbox(label="Pattern text", lines=16, placeholder="Paste your pattern here, one row per line", value=example)
                with gr.Column(scale=1):
                    upload = gr.File(
                        label="…or upload .txt / .md / .pdf, or a photo of a printed pattern",
                        file_types=[".txt", ".md", ".pdf", *photo_reader.IMAGE_TYPES],
                        type="filepath",
                    )
                    go = gr.Button("Check stitch counts", variant="primary")
            summary = gr.Markdown()
            details = gr.HTML()
            chart = gr.Plot(label="Silhouette: stitches made per row (error rows are hatched red and labelled)")
            table = gr.Dataframe(headers=COLUMNS[1:], label="Every row", wrap=True, interactive=False)
            files = gr.File(label="Download report (Markdown, HTML)", file_count="multiple")
            go.click(run_check, [text, upload], [summary, details, chart, table, files, text, upload])

        with gr.Tab("Stuck on a row"):
            gr.Markdown("Is the pattern wrong, or am I? Enter how many stitches you had at the end of the previous row and paste the row you're stuck on.")
            with gr.Row():
                prev = gr.Number(label="Stitches at the end of the previous row", value=24, precision=0)
                row = gr.Textbox(label="The row", value="Rnd 5: (sc 3, inc) x6 (31)")
            ask = gr.Button("Check this row", variant="primary")
            answer = gr.Markdown()
            explain = gr.Markdown()
            ask.click(run_row, [prev, row], [answer, explain])

        gr.HTML(f'<p class="sp-footer">{FOOTER} Rows StitchProof can\'t read are marked CAN\'T CHECK with the reason.</p>')
    return demo


def main() -> None:
    demo = build()
    demo.launch(server_name="127.0.0.1", share=False, css=CSS, footer_links=[])


if __name__ == "__main__":
    main()
