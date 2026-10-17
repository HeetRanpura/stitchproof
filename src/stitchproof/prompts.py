"""THE shared prompts. Used identically for base-model eval, training data, fine-tuned eval and the app."""
from __future__ import annotations

SYSTEM_PROMPT = """Convert ONE line of a US-terms crochet pattern to a JSON stitch program. Output only JSON. Omit fields at their default.
{"kind":"row|round|foundation|note|unsupported","label","range_start","range_end","start":{"type":"continue|magic_ring|chain","chain_count","skip_chains","skipped_count_as_stitch":false},"ops":[],"must_use_all":true,"stated_count","unsupported_reason"}
Ops, written {"t":name,...}:
work{stitch,n}: 1 st in each of next n
into_one{stitch,k}: k sts in 1 st (inc: sc,k=2)
together{stitch,k}: k sts together (dec/sc2tog/invdec: sc,k=2)
skip{n}
work_rest{stitch,leave}: 1 st in each remaining st; leave=L for "to last L st"
turning_chain{n,counts_as_stitch}
repeat{times,body}: no times for "around"/"to end"
Example: "Rnd 3: (sc, inc) x6 (18)" -> {"kind":"round","label":"Rnd 3","ops":[{"t":"repeat","times":6,"body":[{"t":"work","stitch":"sc","n":1},{"t":"into_one","stitch":"sc","k":2}]}],"stated_count":18}
Rules:
- Transcribe exactly. Never fix or compute counts. stated_count = the count written ("(18)", "[18 sts]", "- 18 st", "you should have 18"), even if wrong.
- label as written ("Rnd 3", "R5-8"); ranges also set range_start/range_end.
- Magic ring or "N sc in 2nd ch from hook": start magic_ring. "Ch N" alone: foundation, start chain with chain_count. Chain + row on one line: start chain.
- "sc in 2nd ch from hook and each ch across": skip_chains 1 (3rd: 2, 4th: 3) + work_rest. skipped_count_as_stitch only if stated.
- Starting/turning chains: turning_chain; counts_as_stitch only if the text says so (it replaces the first st; "skip first st" adds nothing). Ignore joining sl st, BLO/FLO/post.
- "rep from * N more times" = N+1 times.
- must_use_all false only if told to leave sts unworked.
- Non-row lines (headings, materials, stuffing, FO, colors, markers): note.
- Chain spaces/lace, multi-size, UK terms, short rows, Tunisian: unsupported + unsupported_reason, label, stated_count."""

USER_TEMPLATE = """Pattern: {header}
Previous line: {prev}
Line: {line}"""


def user_message(header: str, prev: str | None, line: str) -> str:
    return USER_TEMPLATE.format(header=header, prev=prev if prev else "(none)", line=line)


def messages_for_line(header: str, prev: str | None, line: str) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message(header, prev, line)},
    ]


# ---------------------------------------------------------------------------
# Direct check (baselines A and B): the whole pattern in, the model judges counts itself.
# ---------------------------------------------------------------------------

DIRECT_SYSTEM_PROMPT = """You are a crochet technical editor. Check the stitch counts of the pattern you are given (US terms).
For every row or round, work out how many stitches its instructions make from the stitches of the previous row, and compare with the count the pattern states. Also flag instructions that need more stitches than are available, leave stitches unworked when worked around/across, or have a repeat that doesn't fit.

Answer with only a JSON object:
{"errors":[{"row":"<the row label exactly as written>","reason":"<short reason>"}]}
If every count is correct, answer {"errors":[]}."""


def direct_messages(pattern_text: str) -> list[dict]:
    return [
        {"role": "system", "content": DIRECT_SYSTEM_PROMPT},
        {"role": "user", "content": pattern_text},
    ]
