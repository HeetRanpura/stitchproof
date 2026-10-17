"""PDF upload: text-layer PDFs are read with pypdf; wrapped rows are rejoined."""
import pytest

gr = pytest.importorskip("gradio")

from stitchproof.app.ui import read_upload  # noqa: E402
from stitchproof.segment import segment  # noqa: E402


def _pdf(lines: list[str]) -> bytes:
    """A minimal one-page PDF with one Helvetica text line per entry."""
    ops = ["BT", "/F1 11 Tf", "14 TL", "50 780 Td"]
    for line in lines:
        esc = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        ops.append(f"({esc}) Tj T*")
    ops.append("ET")
    stream = "\n".join(ops).encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def test_pdf_text_is_read_and_wrapped_rows_rejoined(tmp_path):
    p = tmp_path / "pattern.pdf"
    p.write_bytes(_pdf(["Tiny Ball", "US terms.", "Rnd 1: 6 sc in MR (6)", "Rnd 2: inc x6 (12)", "Rnd 3: sc, inc, sc, inc, sc, inc,", "sc, inc, sc, inc, sc, inc (18)"]))
    text, merge = read_upload(str(p))
    assert merge is True
    assert "Rnd 2: inc x6 (12)" in text
    lines = [l.text for l in segment(text, merge_wrapped=True).lines]
    assert "Rnd 3: sc, inc, sc, inc, sc, inc, sc, inc, sc, inc, sc, inc (18)" in lines
    assert len(lines) == 5


def test_pdf_without_text_layer_asks_for_paste(tmp_path):
    p = tmp_path / "scan.pdf"
    p.write_bytes(_pdf([]))
    with pytest.raises(gr.Error):
        read_upload(str(p))


def test_txt_and_md_uploads(tmp_path):
    p = tmp_path / "p.md"
    p.write_text("# Ball\nRnd 1: 6 sc in MR (6)\n")
    text, merge = read_upload(str(p))
    assert merge is False and "Rnd 1" in text
