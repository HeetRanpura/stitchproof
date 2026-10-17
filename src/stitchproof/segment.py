"""Split pattern text into lines and build the short header each line is parsed with."""
from __future__ import annotations

import re
from dataclasses import dataclass

_LABEL_RE = re.compile(
    r"^\s*(?:(?:rnds?|rounds?|rows?|r)\s*\.?\s*\d+|\d+\s*[\)\.:-])", re.IGNORECASE
)
_BULLET_RE = re.compile(r"^\s*(?:[-•·▪]|\d+\.(?=\s+[A-Z]))\s+")
_WS_RE = re.compile(r"[ \t ]+")


@dataclass
class PatternLine:
    index: int
    text: str
    prev_text: str | None


@dataclass
class Segmented:
    header: str
    lines: list[PatternLine]


def looks_like_row(text: str) -> bool:
    return bool(_LABEL_RE.match(text))


def clean_line(text: str) -> str:
    text = _WS_RE.sub(" ", text).strip()
    if not looks_like_row(text):
        text = _BULLET_RE.sub("", text)
    return text


def build_header(text: str) -> str:
    """Title + terms + construction, if the pattern states them."""
    raw_lines = [clean_line(l) for l in text.splitlines()]
    raw_lines = [l for l in raw_lines if l]
    parts: list[str] = []
    if raw_lines and not looks_like_row(raw_lines[0]) and len(raw_lines[0]) <= 80:
        parts.append(f"Title: {raw_lines[0]}")
    lower = text.lower()
    if re.search(r"\buk\s+(terms|terminology)\b", lower):
        parts.append("UK terms")
    elif re.search(r"\bus\s+(terms|terminology)\b", lower):
        parts.append("US terms")
    if "spiral" in lower or "continuous round" in lower:
        parts.append("worked in spiral rounds")
    elif re.search(r"joined rounds|join with (a )?sl", lower):
        parts.append("worked in joined rounds")
    elif re.search(r"worked (flat |back and forth )?in rows", lower):
        parts.append("worked in rows")
    return " | ".join(parts) if parts else "(no header)"


def _merge_wrapped(lines: list[str]) -> list[str]:
    """Rejoin rows that a PDF wrapped onto the next line (continuation starts lowercase)."""
    out: list[str] = []
    for line in lines:
        if (
            out
            and looks_like_row(out[-1])
            and not out[-1].rstrip().endswith((")", "]", ".", "!"))
            and line[:1].islower()
            and not looks_like_row(line)
        ):
            out[-1] = f"{out[-1]} {line}"
        else:
            out.append(line)
    return out


def segment(text: str, merge_wrapped: bool = False) -> Segmented:
    lines = [clean_line(l) for l in text.splitlines()]
    lines = [l for l in lines if l]
    if merge_wrapped:
        lines = _merge_wrapped(lines)
    out = [PatternLine(index=i, text=l, prev_text=lines[i - 1] if i else None) for i, l in enumerate(lines)]
    return Segmented(header=build_header(text), lines=out)
