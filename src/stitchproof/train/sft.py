"""LoRA SFT of Qwen3.5-4B on the line-parse examples, using the tinker-cookbook supervised loop.

    python -m stitchproof.train.sft --dry-run     # token count and cost estimate only
    python -m stitchproof.train.sft               # train (asks for confirmation over the budget limit)

Loss is on the assistant message only. Writes the checkpoint paths to train/runs.json and
the train/val loss curve to eval/results/loss_curve.json.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
from pathlib import Path

import chz
from tinker_cookbook.supervised.types import ChatDatasetBuilder

from ..tinker_io import BASE_MODEL, renderer_name_for

TRAIN = Path("data/generated/train.jsonl")
VAL = Path("data/generated/val.jsonl")
RUNS = Path("train/runs.json")
LOG_DIR = Path("train/logs")
TRAIN_PRICE_PER_M = 0.737  # US$ per million training tokens for Qwen3.5-4B (recheck in the Tinker console)

LORA_RANK = 32
EPOCHS = 1  # spec says 2; cut to 1 to fit the remaining credit (see README)
EVAL_EVERY = 45
SAVE_EVERY = 60
BATCH_SIZE = 8
MAX_LENGTH = 2048


def _read(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def count_tokens(rows: list[dict]) -> int:
    from tinker_cookbook import renderers
    from tinker_cookbook.renderers import TrainOnWhat
    from tinker_cookbook.supervised.data import conversation_to_datum
    from tinker_cookbook.tokenizer_utils import get_tokenizer

    tok = get_tokenizer(BASE_MODEL)
    r = renderers.get_renderer(renderer_name_for(BASE_MODEL), tok, model_name=BASE_MODEL)
    total = 0
    for row in rows:
        d = conversation_to_datum(row["messages"], r, MAX_LENGTH, TrainOnWhat.LAST_ASSISTANT_MESSAGE)
        total += d.model_input.length
    return total


@chz.chz
class TwoFileBuilder(ChatDatasetBuilder):
    """Train on one JSONL file, compute val NLL on another (the cookbook builder splits a single file)."""

    train_path: str
    val_path: str
    shuffle_seed: int = 0

    def __call__(self):
        import datasets
        from tinker_cookbook.renderers import TrainOnWhat
        from tinker_cookbook.supervised.data import SupervisedDatasetFromHFDataset, conversation_to_datum

        cc = self.common_config
        renderer = self.renderer

        def load(path):
            return datasets.Dataset.from_list([{"messages": r["messages"]} for r in _read(Path(path))])

        def map_fn(row):
            return conversation_to_datum(row["messages"], renderer, cc.max_length, TrainOnWhat.LAST_ASSISTANT_MESSAGE)

        train_ds = load(self.train_path).shuffle(seed=self.shuffle_seed)
        val_ds = load(self.val_path)
        return (
            SupervisedDatasetFromHFDataset(train_ds, batch_size=cc.batch_size, map_fn=map_fn),
            SupervisedDatasetFromHFDataset(val_ds, batch_size=len(val_ds), map_fn=map_fn),
        )


def estimate() -> tuple[int, int, float]:
    """Training tokens for all epochs plus the val-NLL passes, priced at the training rate (upper bound)."""
    train_rows = _read(TRAIN)
    tokens = count_tokens(train_rows)
    steps = math.ceil(len(train_rows) / BATCH_SIZE) * EPOCHS
    val_passes = steps // EVAL_EVERY + 1
    total = tokens * EPOCHS + count_tokens(_read(VAL)) * val_passes
    return len(train_rows), total, total / 1e6 * TRAIN_PRICE_PER_M


def _collect_outputs(log_dir: Path) -> dict:
    """Read the cookbook's metrics and checkpoint records; pick the final and best-val checkpoints."""
    metrics = [json.loads(l) for l in (log_dir / "metrics.jsonl").read_text().splitlines() if l.strip()]
    ckpts = [json.loads(l) for l in (log_dir / "checkpoints.jsonl").read_text().splitlines() if l.strip()]
    curve = []
    for m in metrics:
        row = {"step": m.get("step")}
        for k, v in m.items():
            if "nll" in k or "loss" in k:
                row[k] = v
        curve.append(row)
    val_key = next((k for m in metrics for k in m if "test" in k and "nll" in k), None)
    sampler_ckpts = [c for c in ckpts if c.get("sampler_path")]
    final = sampler_ckpts[-1] if sampler_ckpts else ckpts[-1]
    best = final
    if val_key:
        val_by_step = {m["step"]: m[val_key] for m in metrics if val_key in m and m.get("step") is not None}
        scored = [(val_by_step.get(c.get("batch", c.get("step"))), c) for c in sampler_ckpts]
        scored = [(v, c) for v, c in scored if v is not None and not math.isnan(v)]
        if scored:
            best = min(scored, key=lambda vc: vc[0])[1]
    return {"curve": curve, "val_key": val_key, "final": final, "best": best, "checkpoints": ckpts}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    ap.add_argument("--max-usd", type=float, default=5.0)
    args = ap.parse_args()

    n, total, cost = estimate()
    print(f"{n} training examples, {EPOCHS} epoch(s), about {total:,} tokens incl. val passes -> about US${cost:.2f} at ${TRAIN_PRICE_PER_M}/M")
    if args.dry_run:
        return
    if cost > args.max_usd:
        raise SystemExit(f"estimate exceeds the US${args.max_usd} limit: shrink the dataset or ask first")
    if not args.yes and input("Start training? [y/N] ").strip().lower() != "y":
        return

    from tinker_cookbook import hyperparam_utils
    from tinker_cookbook.supervised import train
    from tinker_cookbook.supervised.types import ChatDatasetBuilderCommonConfig

    renderer_name = renderer_name_for(BASE_MODEL)
    common = ChatDatasetBuilderCommonConfig(
        model_name_for_tokenizer=BASE_MODEL,
        renderer_name=renderer_name,
        max_length=MAX_LENGTH,
        batch_size=BATCH_SIZE,
    )
    lr = hyperparam_utils.get_lr(BASE_MODEL)
    steps_per_epoch = math.ceil(n / BATCH_SIZE)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    cfg = train.Config(
        log_path=str(LOG_DIR / "v1"),
        model_name=BASE_MODEL,
        recipe_name="stitchproof_sft_v1",
        renderer_name=renderer_name,
        dataset_builder=TwoFileBuilder(common_config=common, train_path=str(TRAIN), val_path=str(VAL)),
        learning_rate=lr,
        lr_schedule="linear",
        num_epochs=EPOCHS,
        lora_rank=LORA_RANK,
        eval_every=EVAL_EVERY,
        save_every=SAVE_EVERY,
        ttl_seconds=None,
    )
    print(f"lr {lr:.2e}, {steps_per_epoch} steps/epoch, logging to {cfg.log_path}")
    asyncio.run(train.main(cfg))

    out = _collect_outputs(Path(cfg.log_path))
    RUNS.parent.mkdir(exist_ok=True)
    RUNS.write_text(
        json.dumps(
            {
                "base_model": BASE_MODEL,
                "renderer": renderer_name,
                "lora_rank": LORA_RANK,
                "epochs": EPOCHS,
                "batch_size": BATCH_SIZE,
                "learning_rate": lr,
                "train_examples": n,
                "train_tokens_estimate": total,
                "final": out["final"],
                "best_val": out["best"],
            },
            indent=1,
        )
    )
    Path("eval/results").mkdir(parents=True, exist_ok=True)
    Path("eval/results/loss_curve.json").write_text(json.dumps({"val_key": out["val_key"], "curve": out["curve"]}, indent=1))
    print(f"final sampler checkpoint: {out['final'].get('sampler_path')}")
    print(f"best-val checkpoint:      {out['best'].get('sampler_path')}")


if __name__ == "__main__":
    main()
