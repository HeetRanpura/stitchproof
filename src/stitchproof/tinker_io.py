"""Thin wrapper around Tinker sampling: renderers, concurrency, a local response cache and token accounting.

Used only for training-time work on synthetic or permitted data (eval, teacher rewrites, OOD writing).
The app never imports this module.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_MODEL = "Qwen/Qwen3.5-4B"
TEACHER_MODEL = "openai/gpt-oss-120b"
OOD_WRITER_MODEL = "moonshotai/Kimi-K2.6"

CACHE_DIR = Path(".stitchproof_cache")

# Renderer per model family. Qwen3.5 answers without a thinking block.
_RENDERERS = {
    "Qwen/Qwen3.5": "qwen3_5_disable_thinking",
    "openai/gpt-oss": "gpt_oss_medium_reasoning",
    "moonshotai/Kimi-K2.6": "kimi_k26_disable_thinking",
    "Qwen/Qwen3.5-397B": "qwen3_5_disable_thinking",
}


def renderer_name_for(model: str) -> str:
    for prefix, name in sorted(_RENDERERS.items(), key=lambda kv: -len(kv[0])):
        if model.startswith(prefix):
            return name
    from tinker_cookbook import model_info

    return model_info.get_recommended_renderer_name(model)


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    calls: int = 0
    cached: int = 0

    def __str__(self) -> str:
        return f"{self.calls} calls ({self.cached} cached), {self.prompt_tokens:,} prompt tokens, {self.completion_tokens:,} completion tokens"


@dataclass
class Sampler:
    model: str  # base model name (for tokenizer/renderer)
    model_path: str | None = None  # tinker:// sampler checkpoint for fine-tuned models
    max_tokens: int = 400
    temperature: float = 0.0
    concurrency: int = 32
    usage: Usage = field(default_factory=Usage)

    def __post_init__(self) -> None:
        load_dotenv()
        import tinker
        from tinker_cookbook import renderers
        from tinker_cookbook.tokenizer_utils import get_tokenizer

        self._tinker = tinker
        self.tokenizer = get_tokenizer(self.model)
        self.renderer = renderers.get_renderer(renderer_name_for(self.model), self.tokenizer, model_name=self.model)
        sc = tinker.ServiceClient()
        if self.model_path:
            self.client = sc.create_sampling_client(model_path=self.model_path)
        else:
            self.client = sc.create_sampling_client(base_model=self.model)
        self._sem = asyncio.Semaphore(self.concurrency)
        CACHE_DIR.mkdir(exist_ok=True)
        tag = hashlib.sha1(f"{self.model}|{self.model_path}|{self.temperature}|{self.max_tokens}".encode()).hexdigest()[:12]
        self._cache_path = CACHE_DIR / f"samples_{tag}.jsonl"
        self._cache: dict[str, str] = {}
        if self._cache_path.exists():
            for line in self._cache_path.read_text().splitlines():
                if line.strip():
                    d = json.loads(line)
                    self._cache[d["k"]] = d["v"]

    def prompt_tokens(self, messages: list[dict]) -> int:
        return self.renderer.build_generation_prompt(messages).length

    async def complete(self, messages: list[dict], cache: bool = True) -> str:
        from tinker_cookbook.renderers import get_text_content

        key = hashlib.sha1(json.dumps(messages, sort_keys=True).encode()).hexdigest()
        if cache and key in self._cache:
            self.usage.cached += 1
            self.usage.calls += 1
            return self._cache[key]
        prompt = self.renderer.build_generation_prompt(messages)
        params = self._tinker.SamplingParams(
            stop=self.renderer.get_stop_sequences(), max_tokens=self.max_tokens, temperature=self.temperature
        )
        async with self._sem:
            for attempt in range(4):
                try:
                    res = await self.client.sample_async(prompt=prompt, num_samples=1, sampling_params=params)
                    break
                except Exception:  # transient API errors: back off and retry
                    if attempt == 3:
                        raise
                    await asyncio.sleep(2 * (attempt + 1))
        seq = res.sequences[0]
        msg, _ = self.renderer.parse_response(seq.tokens)
        text = get_text_content(msg)
        self.usage.calls += 1
        self.usage.prompt_tokens += prompt.length
        self.usage.completion_tokens += len(seq.tokens)
        if cache:
            self._cache[key] = text
            with self._cache_path.open("a") as f:
                f.write(json.dumps({"k": key, "v": text}) + "\n")
        return text

    async def complete_many(self, batch: list[list[dict]]) -> list[str]:
        return await asyncio.gather(*(self.complete(m) for m in batch))


def estimate_tokens(sampler_model: str, batch: list[list[dict]], max_out: int) -> tuple[int, int]:
    """(prompt tokens, worst-case completion tokens) for a batch, without calling the API."""
    from tinker_cookbook import renderers
    from tinker_cookbook.tokenizer_utils import get_tokenizer

    tok = get_tokenizer(sampler_model)
    r = renderers.get_renderer(renderer_name_for(sampler_model), tok, model_name=sampler_model)
    return sum(r.build_generation_prompt(m).length for m in batch), max_out * len(batch)
