# StitchProof

**A local tech editor for crochet patterns.** Paste a pattern and StitchProof checks every stitch count, row by row, on your own computer.

General chatbots are famously bad at crochet: ask one to check a pattern and it will happily "count" stitches it never counted. StitchProof splits the job in two:

1. **A small open-weight model only translates notation.** A fine-tuned Qwen3.5-4B reads each written row ("Rnd 5: (sc 3, inc) x6 (30)") and transcribes it into a precise stitch program. It never counts, and it never "fixes" a number.
2. **Plain code does all the counting.** A deterministic simulator works through the programs row by row and flags every place where the stated count doesn't match what the instructions actually make.

Every flag is therefore verifiable: the explanation always shows the numbers ("Rnd 5 says (31), but '(sc 3, inc) x6' uses 24 of 24 stitches and makes 30.").

## Who it's for

- **Designers (the paid tier in the business story):** check a whole draft before publishing it on Etsy or Ravelry. You get a row-by-row table, a "silhouette" chart of stitch counts (an error shows up as a dent or spike), and a Markdown/HTML report. This is the stitch-math part of what a human tech editor checks.
- **Makers (free):** stuck mid-project? Enter your previous row's count and paste the row. StitchProof answers "The pattern says X. These instructions make Y from your Z stitches", i.e. whether the pattern is wrong or you are.

Pricing is a hypothesis, not a claim: makers free (distribution), designers paying per pattern check or a small monthly fee.

## How it works

```
pattern text ──segment──▶ lines ──fine-tuned 4B model──▶ stitch programs (JSON) ──simulator──▶ OK / ERROR / WARNING / CAN'T CHECK
                          (+ header, previous line)       (transcription only)          (code: all counting, explanations)
```

- `src/stitchproof/schema.py`: the stitch program (work, increase, decrease, skip, "to end", turning chain, repeat).
- `src/stitchproof/simulate.py`: the counting engine. Error codes: COUNT_MISMATCH, OVERFLOW, LEFTOVER, REPEAT_REMAINDER; NO_STATED_COUNT (warning); CANT_CHECK.
- [CONVENTIONS.md](CONVENTIONS.md): the counting rules, one test each.
- `src/stitchproof/generate/`: synthetic training and eval data, generated entirely by our own code (no published patterns are used anywhere).
- `src/stitchproof/train/sft.py`: LoRA fine-tune on [Tinker](https://thinkingmachines.ai/tinker/).
- `src/stitchproof/eval/`: the A/B/C/D comparison.
- `src/stitchproof/app/`: the local Gradio app.

## Results

Four approaches, the same eval sets, the same prompt and the same parser (temperature 0):

| ID | Approach |
| --- | --- |
| A | Base Qwen3.5-4B, asked directly to find count errors in the whole pattern |
| B | gpt-oss-120b asked the same way (a much larger model, reference only, run on 15 patterns) |
| C | Base Qwen3.5-4B transcribing each line + the simulator |
| D | Fine-tuned Qwen3.5-4B transcribing each line + the simulator |

![Errors caught and false alarms per approach](eval/results/headline.png)

| | A: base, direct | B: teacher, direct (ref.) | C: base + simulator | D: fine-tuned + simulator |
| --- | --- | --- | --- | --- |
| **eval_synth: errors caught** | 44.4% (20/45) | 54.5% (6/11) | 75.6% (34/45) | **95.6% (43/45)** |
| **eval_synth: false alarms** | 13.7% (78/571) | 38.3% (62/162) | 42.6% (243/571) | **22.2% (127/571)** |
| **OOD: errors caught** | 61.1% (11/18) | – | 100.0% (18/18) | **100.0% (18/18)** |
| **OOD: false alarms** | 11.2% (23/205) | – | 50.7% (104/205) | **8.3% (17/205)** |
| OOD: pattern-level accuracy | 32.0% (8/25) | – | 16.0% (4/25) | **80.0% (20/25)** |
| eval_synth: valid JSON | 86.7% (52/60) | 100.0% (15/15) | 78.0% (663/850) | **100.0% (850/850)** |
| eval_synth: stated-count faithfulness | – | – | 67.4% (415/616) | **100.0% (616/616)** |

- **eval_synth**: 60 patterns written only in four notation styles that never appear in training, a third of them cones (a shape never seen in training).
- **OOD**: 25 patterns whose text was written by Kimi-K2.6, a third model family, from the structure alone.
- Errors caught = seeded error rows flagged ERROR / all seeded error rows. False alarms = clean rows flagged ERROR / all clean rows.

**The one weak spot, measured:** almost all of D's false alarms on eval_synth come from a single held-out style, `*sc, inc; rep from * 4 more times`, which means 5 repeats; D transcribes it as 4. On those lines D raises false alarms on 97.5% (115/118) of clean rows. On lines in the other three held-out styles it parses 99.8% (466/467) exactly, with 2.7% (12/438) false alarms. We did not retrain on it, because that would be tuning on the eval set; the next version adds that style to the training templates. Full tables, per-error-type results and C/D disagreements: [eval/results/summary.md](eval/results/summary.md).

**Training:** LoRA rank 32 on Qwen3.5-4B with Tinker, 1 epoch over 1,410 line examples. The examples come from three sources: our code templates (60 patterns) and rewrites by two teacher model families, gpt-oss-120b and Qwen3.5-397B (43 patterns). Val loss went from 0.303 to 0.0028. The whole build used US$1.62 of Tinker credit ([eval/results/costs.md](eval/results/costs.md)); the spec's 2 epochs and ~3,000 lines were cut to fit the remaining budget.

**Local model:** a Q4_K_M base built from the official Qwen weights plus the LoRA (2.93 GB on disk, 3.18 GB RAM, about 2.4 s per line on an M4 MacBook) agrees with the Tinker-hosted model on 100.0% (50/50) of val lines. See [eval/results/export.md](eval/results/export.md).

Example output: [docs/example_report.md](docs/example_report.md).

![Silhouette chart: stitch counts row by row for a small ball, with two error rounds hatched and labelled](docs/screenshots/silhouette_example.png)

## Run it locally

```bash
uv venv --python 3.11 && uv pip install -e ".[app,dev]"
pytest -q
```

The app needs the fine-tuned model running locally through llama.cpp: the 4-bit base GGUF plus the StitchProof LoRA, built by `python -m stitchproof.train.export download|peft|gguf` (see [eval/results/export.md](eval/results/export.md)).

```bash
llama-server -m models/stitchproof-base-q4_k_m.gguf --lora models/stitchproof-lora-v1.gguf --port 8080 --host 127.0.0.1 --jinja -c 4096 -np 1
python -m stitchproof.app.ui
```

Open http://127.0.0.1:7860. To try the interface without a model, `STITCHPROOF_BACKEND=replay` replays gold answers for the synthetic example patterns. (An Ollama backend exists, `STITCHPROOF_BACKEND=ollama`, but isn't tested with the LoRA yet.)

**Fully offline:** once the GGUF files are on disk, turn Wi-Fi off and start the two commands above. The app binds to 127.0.0.1 only, has Gradio analytics disabled, and sends nothing anywhere. Parsed lines are cached in `~/.stitchproof_cache/` on your machine, so re-checking an edited pattern is fast.

## Reproduce the data, training and eval

```bash
cp .env.example .env    # add TINKER_API_KEY
python -m stitchproof.generate.build_dataset --train-lines 1400 --val-lines 120    # template splits (fixed seed)
python -m stitchproof.generate.paraphrase                    # rewrites by two teacher families
python -m stitchproof.generate.build_dataset --train-lines 1400 --val-lines 120 --paraphrased data/generated/paraphrased.jsonl
python -m stitchproof.generate.ood                           # out-of-generator eval set
python -m stitchproof.train.sft --dry-run                    # token and cost estimate
python -m stitchproof.train.sft
python -m stitchproof.eval.run_eval --approach C --set synth  # likewise A, B, D and --set ood
python -m stitchproof.eval.report
python -m stitchproof.eval.equivalence --n 50                 # with llama-server running
```

Every script prints a cost estimate first and stops above a budget limit.

## Limitations

- Training data is synthetic. No real designer drafts have been evaluated yet (`data/real/` is set up for permitted drafts and never committed).
- Notation the model has never seen can trip it up: "rep from * N more times" is the measured example (see Results).
- v1 covers US terms, amigurumi rounds and flat rows with common stitches. Lace and chain spaces, multi-size patterns, UK terms, short rows, Tunisian crochet and charts are marked CAN'T CHECK with a reason.
- Counting conventions vary between designers; StitchProof follows [CONVENTIONS.md](CONVENTIONS.md).
- It checks stitch math only, not gauge, fit or the look of the finished piece.
- Other crochet tools exist (AI pattern generators, chart renderers, stitch counters). StitchProof's difference is automated, local checking of a designer's own draft, with a fine-tune whose improvement is measured by code.

The translate → simulate → verify design should carry over to knitting; that isn't built.

## License

Code: MIT (see [LICENSE](LICENSE)). The base model, Qwen3.5-4B, is distributed under its own license; check the model card before redistributing weights.
