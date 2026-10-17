# StitchProof counting conventions (v1)

These are the rules the simulator (`src/stitchproof/simulate.py`) follows. Every rule has at least one test in `tests/test_simulate.py` (marked with its rule number). Designers do not all count the same way; when a pattern disagrees with these rules, StitchProof follows these rules, and the explanation always shows the numbers so a human can judge.

**US crochet terms only.** UK-terms patterns are marked CAN'T CHECK.

## 1. One stitch in one stitch
sc, hdc, dc, tr and sl st worked into a stitch use 1 stitch and make 1. Bobble, popcorn, puff and cluster stitches also count as 1 made from 1 used.

## 2. Increases
"inc" means 2 stitches in one stitch (uses 1, makes 2). "3 sc in next st" uses 1 and makes 3. The same applies to any stitch type ("2 dc in next st").

## 3. Decreases
"dec", "sc2tog", "invdec" and "invisible decrease" use 2 and make 1. "sc3tog" and "dc3tog" use 3 and make 1.

## 4. Loop modifiers
FLO, BLO, back bump and front/back post never change counts.

## 5. Magic ring
For "6 sc in MR" (also magic circle or adjustable ring), the stitches are worked into the ring: nothing is used and 6 are made. "Ch 2, 6 sc in 2nd ch from hook" is treated the same way. A repeat "around" or "sc in each st around" cannot be worked into a ring and is CAN'T CHECK.

## 6. Foundation chain
"Ch N" makes N chains. "sc in 2nd ch from hook" skips 1 chain, "hdc in 3rd ch from hook" skips 2 and "dc in 4th ch from hook" skips 3. Skipped chains do **not** count as a stitch unless the text says so (e.g. "skipped ch count as dc"). When they do count, they add 1 to the row's count.

Example: "Ch 11. Row 1: sc in 2nd ch from hook and in each ch across (10)" gives 11 − 1 = 10 stitches available, and 10 are made.

## 7. Turning chains
"ch 1, turn" and "ch 2, turn" do not count as a stitch unless the text says so ("counts as a st", "counts as dc"). A turning chain that counts is worked in place of the first stitch of the row: it **uses 1 and makes 1**. "Skip the first st" or "sk st at base of ch" is part of that turning chain, not an extra skip.

Example: 12 stitches, "Ch 3 (counts as dc), dc in next st and in each st across (12)": the ch 3 uses 1 and makes 1, then 11 dc use 11 and make 11, so 12 are made.

## 8. Joined rounds
The joining sl st and the starting ch 1 of a joined round do not count. Spiral and joined rounds count the same.

## 9. Around / across / to end
A row worked "around", "across" or "to end" must use exactly all the available stitches. Using fewer is **LEFTOVER** (unless the text says to leave stitches unworked); needing more is **OVERFLOW**.

## 10. Repeats
"(sc, inc) x6", "*sc, inc* 6 times", "[sc 1, inc] around", "rep from * around" and "rep from * to end" are all repeats. A repeat with a number is worked that many times. A repeat worked "around" or "to end" continues until the stitches run out, and must divide the available stitches exactly; otherwise it is **REPEAT_REMAINDER**.

## 11. Row ranges
"Rnd 5-10: sc around (24)" means the same instructions for each row in the range, and the stated count applies to each row. Each row in the range starts from the previous row's count.

## 12. Stated counts
"(18)", "[18]", "(18 sts)", "(18 sc)", "- 18 st", "18 stitches" and "you should have 18" are all stated counts. A row with no stated count gets a WARNING (NO_STATED_COUNT) only, never an error. Foundation chains need no stated count.

## 13. Notes
Lines that are not rows ("Stuff firmly", "FO, leave a long tail", "Change to color B", "Place a stitch marker", headings, materials) are notes and are ignored for counting. A note does not break the count between the rows around it.

## 14. Out of scope in v1 (always CAN'T CHECK, with a reason)
Chain spaces and lace ("ch-sp", "ch 2, skip 2"), working both sides of a foundation chain (oval starts), multi-size patterns ("(S, M, L)", "36 (40, 44)"), UK terms, short rows, Tunisian crochet, charts, and anything the model marks as unsupported.

## 15. After an error or a line that can't be checked
- **Starting count after a wrong row.** When a row's instructions don't produce its stated count, the next row is checked first from what the instructions actually made. If that fails but the row works from the designer's stated count, it is checked from the stated count instead, and the explanation says so. One mistake is reported once and doesn't cascade through the rest of the pattern.
- **After a CAN'T CHECK line.** If the line has a stated count, the next row starts from it. If it doesn't, the following rows are CAN'T CHECK ("the starting count is unknown") until a magic ring, a starting chain, or a stated count gives a known count again.
- **A row with no starting point.** A row that comes before any magic ring or foundation chain is CAN'T CHECK.

## Error and warning codes

| Code | Level | Meaning |
| --- | --- | --- |
| COUNT_MISMATCH | ERROR | stitches made ≠ stated count |
| OVERFLOW | ERROR | instructions need more stitches than are available |
| LEFTOVER | ERROR | row worked across/around but stitches are left unworked |
| REPEAT_REMAINDER | ERROR | an "around" repeat doesn't divide the available stitches |
| NO_STATED_COUNT | WARNING | the row has no stated count |
| CANT_CHECK | INFO | unsupported line, or previous count unknown |
