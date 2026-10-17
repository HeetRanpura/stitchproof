# Draft post: StitchProof

> Draft for the DEV Hacktoberfest 2026 Open-Source AI Challenge, Week 2 ("Side Hustle"). Every number below is copied from `eval/results/` (summary.md, export.md, costs.md). Edit freely, but keep the numbers tied to those files.

**Title:** StitchProof: I taught a 4B model to read crochet patterns, and let plain code do the counting

**Tags:** #hacktoberfest #ai #opensource #python

---

## AI can't crochet, so it shouldn't count

Ask a chatbot to check a crochet pattern and it will cheerfully "count" stitches it never counted. I tried it with the open-weight Qwen3.5-4B. Given 60 test patterns and asked directly to find the rows whose stitch counts are wrong, it caught **44.4% (20/45)** of the mistakes.

That matters to real people. Designers sell PDF patterns on Etsy and Ravelry and pay human tech editors to check every stitch count before publishing, because a wrong count in round 5 means a maker unravels an evening's work, and errata are a recurring headache.

## The design: the model translates, code counts

StitchProof splits the job in two:

1. **A fine-tuned Qwen3.5-4B only translates notation.** Each row ("Rnd 5: (sc 3, inc) x6 (30)") becomes a small JSON stitch program. It transcribes exactly what's written, including a wrong stated count, and never does arithmetic.
2. **A deterministic simulator does all the counting.** It walks the programs row by row and flags every place where the stated count doesn't match what the instructions make, or where a row needs more stitches than exist, leaves some unworked, or has a repeat that doesn't fit.

Every flag comes with the numbers: *"Rnd 5 says (31), but '(sc 3, inc) x6' uses 24 of 24 stitches and makes 30."* You don't have to trust the AI; you can check its arithmetic, because there isn't any.

[screenshot: the app, "Check a pattern" tab with two errors flagged]

![Silhouette chart](screenshots/silhouette_example.png)

The "silhouette" chart plots stitches per round. For amigurumi it looks like the outline of the piece, so a mistake shows up as a dent.

## Results

I compared four approaches on the same patterns, with the same prompt and parser:

| | A: base, asked directly | C: base model + simulator | D: fine-tuned + simulator |
| --- | --- | --- | --- |
| Errors caught (held-out styles) | 44.4% (20/45) | 75.6% (34/45) | **95.6% (43/45)** |
| False alarms (held-out styles) | 13.7% (78/571) | 42.6% (243/571) | **22.2% (127/571)** |
| Errors caught (written by another model family) | 61.1% (11/18) | 100.0% (18/18) | **100.0% (18/18)** |
| False alarms (written by another model family) | 11.2% (23/205) | 50.7% (104/205) | **8.3% (17/205)** |

- The **held-out** set (60 patterns) uses four notation styles and a shape (cones) that never appear in training.
- The **out-of-generator** set (25 patterns) was written by Kimi-K2.6, a third model family, from the pattern structure alone.
- I also asked gpt-oss-120b, a much larger model, to check 15 of the held-out patterns directly. It caught 54.5% (6/11) of the errors with 38.3% (62/162) false alarms. Size alone doesn't fix "asked to count".

The base model plus simulator (C) catches a lot of errors, but it raises false alarms on 42.6% of clean rows, because it can't write the format reliably: only 78.0% (663/850) of its outputs are valid JSON. The fine-tune gets 100.0% (850/850) valid JSON and copies the stated count faithfully on 100.0% (616/616) of rows.

[chart: eval/results/headline.png]

### Where it still fails (honestly)

Almost all of the fine-tune's false alarms on the held-out set come from a single notation it never saw: `*sc, inc; rep from * 4 more times`, which means 5 repeats in total. The model writes 4. On those rows it raises false alarms on 97.5% (115/118) of clean rows. On rows in the other three unseen styles it parses 99.8% (466/467) exactly, with 2.7% (12/438) false alarms. I didn't retrain on that style, because that would be tuning on the test set; it goes into the next version's training templates.

## How it's built (Tinker)

- **Data:** no published patterns anywhere. My own generators build pattern structures (spheres, tubes, cones, flat pieces, triangles, mixed stitches), seed known errors and render them in many notation styles. Two teacher models, gpt-oss-120b and Qwen3.5-397B, rewrote a share of the patterns in a natural designer voice, with every number and row label checked in code.
- **Training:** LoRA rank 32 on Qwen3.5-4B with Tinker's cookbook, 1,410 line examples, one epoch. Validation loss went from 0.303 to 0.0028.
- **Cost:** the whole build (data, baselines, training and evaluation) used **US$1.62** of Tinker credit.

## It runs on your laptop

Patterns are a designer's unreleased work, so StitchProof runs locally. I exported the LoRA from Tinker, converted it for llama.cpp and run it on a 4-bit base:

- 2.93 GB on disk, 3.18 GB of RAM, about 2.4 s per row on an M4 MacBook
- **100.0% (50/50)** agreement with the Tinker-hosted model on validation rows
- the app binds to localhost only and sends nothing anywhere: turn Wi-Fi off and it still works

One gotcha worth sharing: Tinker trains Qwen3.5's linear-attention Q, K and V projections as separate LoRAs, but the model stores them fused. I rebuilt an exact fused LoRA (stacked A matrices, block-diagonal B matrices, rescaled for llama.cpp's alpha/rank) so llama.cpp could load it.

## Two modes, one engine

- **Designers:** paste or upload a whole draft (.txt, .md or PDF) and get a row-by-row table, the silhouette chart and a Markdown/HTML report. (Business idea: designers pay per pattern check.)
- **Makers:** stuck mid-project? Enter your previous stitch count and paste the row: *"The pattern says 31. These instructions make 30 from your 24 stitches. The pattern itself doesn't add up here, so it's not you."* (Free.)

## Limitations

- Training data is synthetic, and no real designer drafts are evaluated yet.
- v1 covers US terms, amigurumi rounds and flat rows. Lace and chain spaces, multi-size patterns, UK terms, short rows and Tunisian crochet are marked CAN'T CHECK with a reason, never guessed.
- It checks stitch math only, not gauge, fit or looks.

The translate → simulate → verify split should carry over to knitting next.

**Code (MIT):** https://github.com/HeetRanpura/stitchproof
