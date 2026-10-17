# Local model export (M5)

Route: LoRA on a 4-bit base, no merge. Built on an Apple M4 MacBook (16 GB RAM).

1. Adapter exported with Tinker's current API (`save_weights_external` + `get_external_weights_urls`). The deprecated archive endpoint hung.
2. Converted to standard PEFT with the cookbook's `build_lora_adapter`.
3. Qwen3.5 linear-attention fix: Tinker trains separate `in_proj_q/k/v` LoRAs, but the model stores a fused `in_proj_qkv` (Q‖K‖V). An exact fused LoRA stacks the A matrices along the rank axis and block-diagonalises the B matrices (rank 96). B is scaled by 3 because llama.cpp scales by alpha / rank. The unembedding LoRA (on the tied `embed_tokens`) is dropped; see the equivalence result below.
4. Base: the official `Qwen/Qwen3.5-4B` safetensors, converted with llama.cpp's `convert_hf_to_gguf.py` (commit d81235049, matching the installed llama.cpp 0.6.0) to Q8_0, then requantized to Q4_K_M. The adapter was converted with `convert_lora_to_gguf.py`. The 9.3 GB bf16 download was deleted afterwards.

| File | Size |
| --- | --- |
| `stitchproof-base-q4_k_m.gguf` | 2.78 GB |
| `stitchproof-lora-v1.gguf` | 0.15 GB |
| `stitchproof-base-q8_0.gguf` (intermediate, optional) | 4.61 GB |

Run:

```bash
llama-server -m models/stitchproof-base-q4_k_m.gguf --lora models/stitchproof-lora-v1.gguf --port 8080 --host 127.0.0.1 --jinja -c 4096 -np 1
```

## Equivalence: local vs Tinker

50 val lines (fixed seed), temperature 0, same prompt and parser: **100.0% (50/50)** of canonicalised programs agree (`equivalence_q4_k_m.json`). The spec's bar is 95%.

## Performance (llama.cpp, Metal, Q4_K_M + LoRA)

| | |
| --- | --- |
| Load time | 2.5 s (server log, to "model loaded") |
| Per-line latency | mean 2.36 s, p50 2.49 s over the 50 lines (one request at a time) |
| Resident memory | 3.18 GB (llama-server RSS after the run) |
| Disk | 2.93 GB (base Q4_K_M + LoRA) |

A 20-line pattern takes about 45 seconds on first check; lines already seen are served from the app's local cache.
