"""Read an uploaded pattern file into text: .txt/.md as-is, .pdf via its text layer, photos via local Gemma.

Shared by the web app server and the Gradio fallback UI; raises InputError with a message
that can be shown to the user as-is.
"""
from __future__ import annotations

from pathlib import Path

from . import photo_reader

TEXT_TYPES = (".txt", ".md", ".markdown")


class InputError(ValueError):
    pass


def read_file(path: str | Path) -> tuple[str, bool, str]:
    """Return (text, merge_wrapped, source) where source is "text", "pdf" or "photo"."""
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix in photo_reader.IMAGE_TYPES:
        try:
            text = photo_reader.transcribe(p)
        except photo_reader.PhotoReaderUnavailable as e:
            raise InputError(f"Reading photos needs Gemma 4 running locally in Ollama ({e}). Please paste the pattern text instead.")
        except OSError as e:
            raise InputError(f"Gemma couldn't read this photo ({type(e).__name__}). Please paste the pattern text instead.")
        if not text.strip():
            raise InputError("Gemma couldn't find any text in this photo. Please paste the pattern text instead.")
        return text, True, "photo"
    if suffix == ".pdf":
        from pypdf import PdfReader

        try:
            reader = PdfReader(str(p))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception as e:  # noqa: BLE001 - pypdf raises many types for broken files
            raise InputError(f"This PDF couldn't be read ({type(e).__name__}). Please paste the pattern text instead.")
        if not text.strip():
            raise InputError("This PDF has no text layer (it may be a scan). Upload a photo of the page or paste the pattern text instead.")
        return text, True, "pdf"
    if suffix in TEXT_TYPES or not suffix:
        return p.read_text(errors="replace"), False, "text"
    raise InputError(f"StitchProof reads .txt, .md, .pdf and photos ({', '.join(photo_reader.IMAGE_TYPES)}); {suffix} isn't supported.")
