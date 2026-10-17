"""Export the fine-tuned adapter and build a local GGUF model (no merge).

    python -m stitchproof.train.export download      # adapter files -> models/adapter/
    python -m stitchproof.train.export peft          # Tinker adapter -> standard PEFT LoRA (models/peft/)
    python -m stitchproof.train.export gguf          # official base -> models/stitchproof-base-*.gguf + LoRA GGUF

Uses Tinker's current export path (save_weights_external + get_external_weights_urls), not
the deprecated archive endpoint, which hangs. The adapter is converted with the cookbook
(Tinker trains some attention weights in a split form, so a raw adapter isn't PEFT-loadable),
then with llama.cpp's convert_lora_to_gguf.py, and applied at runtime with
`llama-server -m <base gguf> --lora <lora gguf>`. Nothing is merged, so no full-size copy is written.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

RUNS = Path("train/runs.json")
MODELS = Path("models")
ADAPTER = MODELS / "adapter"
PEFT = MODELS / "peft"
PEFT_FUSED = MODELS / "peft-fused"  # llama.cpp-ready: Qwen3.5 split Q/K/V LoRAs fused into in_proj_qkv
HF_BASE = MODELS / "hf" / "Qwen3.5-4B"
LLAMA_CPP = MODELS / "llama.cpp"  # sparse checkout of ggml-org/llama.cpp (conversion scripts only)
BASE_Q8 = MODELS / "stitchproof-base-q8_0.gguf"
BASE_Q4 = MODELS / "stitchproof-base-q4_k_m.gguf"
LORA_GGUF = MODELS / "stitchproof-lora-v1.gguf"


def download() -> None:
    load_dotenv()
    import tinker

    runs = json.loads(RUNS.read_text())
    sc = tinker.ServiceClient()
    ext_path = runs.get("external_weights_path")
    if not ext_path:
        tc = sc.create_training_client_from_state(runs["final"]["state_path"])
        res = tc.save_weights_external("stitchproof-v1", ttl_seconds=30 * 24 * 3600).result()
        ext_path = res.path
        runs["external_weights_path"] = ext_path
        RUNS.write_text(json.dumps(runs, indent=1))
    print(f"external weights: {ext_path}")
    urls = sc.create_rest_client().get_external_weights_urls(ext_path).result().urls
    ADAPTER.mkdir(parents=True, exist_ok=True)
    for rel, url in urls.items():
        dest = ADAPTER / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        _fetch(url, dest)
        print(f"  {rel}: {dest.stat().st_size / 1e6:.1f} MB")


def _fetch(url: str, dest: Path, tries: int = 8) -> None:
    """Download with resume (HTTP Range) and retries; signed URLs drop long transfers."""
    import time

    total = None
    for attempt in range(tries):
        have = dest.stat().st_size if dest.exists() else 0
        req = urllib.request.Request(url, headers={"Range": f"bytes={have}-"} if have else {})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                if r.status == 200:
                    have = 0  # server ignored the range: start over
                cr = r.headers.get("Content-Range")
                total = int(cr.split("/")[-1]) if cr else int(r.headers.get("Content-Length", 0)) + have
                with dest.open("ab" if have else "wb") as f:
                    shutil.copyfileobj(r, f, 1 << 20)
            if total and dest.stat().st_size >= total:
                return
        except urllib.error.HTTPError as e:
            if e.code == 416:  # already complete
                return
            if attempt == tries - 1:
                raise
        except (OSError, TimeoutError):
            if attempt == tries - 1:
                raise
        time.sleep(2 * (attempt + 1))


def peft() -> None:
    from tinker_cookbook import weights

    if PEFT.exists():
        shutil.rmtree(PEFT)
    weights.build_lora_adapter(base_model=str(HF_BASE), adapter_path=str(ADAPTER), output_path=str(PEFT))
    print(f"PEFT adapter in {PEFT}: {sorted(p.name for p in PEFT.iterdir())}")


def fuse_qkv(drop_unembed: bool = True) -> None:
    """Make the PEFT adapter loadable by llama.cpp for Qwen3.5.

    Tinker trains separate in_proj_q/k/v LoRAs on the linear-attention layers, but the model
    stores one fused in_proj_qkv (Q‖K‖V by rows). An exact LoRA for the fused weight stacks the
    A matrices along the rank axis and puts the B matrices on a block diagonal (rank 3r).
    llama.cpp scales each LoRA by alpha / rank, so B is multiplied by 3 to keep the scale at
    alpha / r. The unembedding LoRA (stored on the tied embed_tokens) is dropped by default,
    because llama.cpp would also apply it to the input embeddings; the equivalence check
    measures the effect.
    """
    import torch
    from safetensors.torch import load_file, save_file

    w = load_file(str(PEFT / "adapter_model.safetensors"))
    cfg = json.loads((PEFT / "adapter_config.json").read_text())
    out: dict[str, torch.Tensor] = {}
    groups: dict[str, dict[str, torch.Tensor]] = {}
    for k, v in w.items():
        if ".linear_attn.in_proj_" in k and any(f".in_proj_{r}.lora_" in k for r in "qkv"):
            prefix, rest = k.split(".linear_attn.in_proj_")
            role, ab = rest[0], rest.split(".lora_")[1][0]
            groups.setdefault(prefix, {})[f"{role}{ab}"] = v
        elif drop_unembed and ".embed_tokens." in k:
            continue
        else:
            out[k] = v
    rank3 = None
    for prefix, g in groups.items():
        a = torch.cat([g["qA"], g["kA"], g["vA"]], dim=0)
        b = torch.block_diag(g["qB"], g["kB"], g["vB"]) * 3.0
        out[f"{prefix}.linear_attn.in_proj_qkv.lora_A.weight"] = a.contiguous()
        out[f"{prefix}.linear_attn.in_proj_qkv.lora_B.weight"] = b.to(g["qB"].dtype).contiguous()
        rank3 = a.shape[0]
    targets = [t for t in cfg["target_modules"] if t not in ("in_proj_q", "in_proj_k", "in_proj_v") and not (drop_unembed and t == "embed_tokens")]
    cfg["target_modules"] = sorted(targets + ["in_proj_qkv"])
    cfg["rank_pattern"] = {"in_proj_qkv": rank3}
    if PEFT_FUSED.exists():
        shutil.rmtree(PEFT_FUSED)
    PEFT_FUSED.mkdir(parents=True)
    save_file(out, str(PEFT_FUSED / "adapter_model.safetensors"))
    (PEFT_FUSED / "adapter_config.json").write_text(json.dumps(cfg, indent=1))
    print(f"fused {len(groups)} linear-attention layers (rank {rank3}); {len(out)} tensors; unembed LoRA {'dropped' if drop_unembed else 'kept'}")


def _run(cmd: list[str]) -> None:
    import os

    print("$", " ".join(cmd))
    env = {**os.environ, "PYTHONPATH": str(LLAMA_CPP / "gguf-py")}  # llama.cpp's own gguf package
    subprocess.run(cmd, check=True, env=env)


def gguf(keep_q8: bool = True) -> None:
    py = sys.executable
    if not BASE_Q8.exists():
        _run([py, str(LLAMA_CPP / "convert_hf_to_gguf.py"), str(HF_BASE), "--outtype", "q8_0", "--outfile", str(BASE_Q8)])
    fuse_qkv()
    _run([py, str(LLAMA_CPP / "convert_lora_to_gguf.py"), str(PEFT_FUSED), "--base", str(HF_BASE), "--outtype", "f16", "--outfile", str(LORA_GGUF)])
    if not BASE_Q4.exists():
        _run(["llama-quantize", "--allow-requantize", str(BASE_Q8), str(BASE_Q4), "Q4_K_M"])
    for p in (BASE_Q8, BASE_Q4, LORA_GGUF):
        if p.exists():
            print(f"{p}: {p.stat().st_size / 1e9:.2f} GB")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["download", "peft", "gguf"])
    args = ap.parse_args()
    {"download": download, "peft": peft, "gguf": gguf}[args.step]()


if __name__ == "__main__":
    sys.exit(main())
