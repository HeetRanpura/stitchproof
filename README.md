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

## Evaluation

Four approaches, the same eval sets, the same prompt and the same parser:

| ID | Approach |
| --- | --- |
| A | Base Qwen3.5-4B, asked directly to find count errors in the whole pattern |
| B | A much larger model asked the same way (reference only) |
| C | Base Qwen3.5-4B transcribing each line + the simulator |
| D | Fine-tuned Qwen3.5-4B transcribing each line + the simulator |

Headline metrics: **errors caught** (seeded error rows flagged) and **false alarms** (clean rows flagged). Results, with counts, are in [eval/results/summary.md](eval/results/summary.md) once the runs are complete.

## Run it locally

```bash
uv venv --python 3.11 && uv pip install -e ".[app,dev]"
pytest -q
```

The app needs the fine-tuned model running locally, either through llama.cpp or through Ollama:

```bash
llama-server -m models/stitchproof-q4_k_m.gguf --port 8080
python -m stitchproof.app.ui
```

```bash
STITCHPROOF_BACKEND=ollama STITCHPROOF_MODEL=stitchproof python -m stitchproof.app.ui
```

Open http://127.0.0.1:7860. To try the interface without a model, `STITCHPROOF_BACKEND=replay` replays gold answers for the synthetic example patterns.

**Fully offline:** once the GGUF file is on disk, turn Wi-Fi off and start the commands above. The app binds to 127.0.0.1 only, has Gradio analytics disabled, and sends nothing anywhere. Parsed lines are cached in `~/.stitchproof_cache/` on your machine so re-checking an edited pattern is fast.

## Reproduce the data, training and eval

```bash
cp .env.example .env    # add TINKER_API_KEY
python -m stitchproof.generate.build_dataset                 # template splits (fixed seed)
python -m stitchproof.generate.paraphrase                    # teacher rewrites for ~35% of train/val
python -m stitchproof.generate.build_dataset --paraphrased data/generated/paraphrased.jsonl
python -m stitchproof.generate.ood                           # out-of-generator eval set
python -m stitchproof.train.sft --dry-run                    # token and cost estimate
python -m stitchproof.train.sft
python -m stitchproof.eval.run_eval --approach C --set synth  # likewise A, B, D and --set ood
python -m stitchproof.eval.report
```

Every script prints a cost estimate first and stops above a budget limit.

## Limitations

- Training data is synthetic; the real-pattern test set is small.
- v1 covers US terms, amigurumi rounds and flat rows with common stitches. Lace and chain spaces, multi-size patterns, UK terms, short rows, Tunisian crochet and charts are marked CAN'T CHECK with a reason.
- Counting conventions vary between designers; StitchProof follows [CONVENTIONS.md](CONVENTIONS.md).
- It checks stitch math only, not gauge, fit or the look of the finished piece.
- Other crochet tools exist (AI pattern generators, chart renderers, stitch counters). StitchProof's difference is automated, local checking of a designer's own draft, with a fine-tune whose improvement is measured by code.

The translate → simulate → verify design should carry over to knitting; that isn't built.

## License

Code: MIT (see [LICENSE](LICENSE)). The base model, Qwen3.5-4B, is distributed under its own license; check the model card before redistributing weights.
