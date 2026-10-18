"""Local inference with the same prompt and parser as training and eval, plus the check pipeline.

Backends (choose with STITCHPROOF_BACKEND):
- "llama" (default): a local llama.cpp server (`llama-server -m stitchproof-q4_k_m.gguf --port 8080`).
- "ollama": a local Ollama model (STITCHPROOF_MODEL, default "stitchproof").
- "replay": developer demo that replays gold programs for the synthetic data files. No model.
- "tinker-demo": CLOUD DEMO MODE. Lines are sent to Tinker. Off unless explicitly chosen,
  and the UI labels it on every page.

Patterns never leave the machine with the local backends. Nothing is logged.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from ..parse_output import ParseResult, parse_model_output
from ..prompts import messages_for_line
from ..schema import LineProgram, to_compact_json
from ..segment import segment
from ..simulate import LineResult, check_single_row, simulate

CACHE_DIR = Path(os.environ.get("STITCHPROOF_CACHE", Path.home() / ".stitchproof_cache"))


class Backend:
    name = "backend"
    is_local = True
    is_demo = False
    concurrency = 4

    def complete(self, messages: list[dict]) -> str:
        raise NotImplementedError


def _post(url: str, body: dict, timeout: float = 120) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


class LlamaServerBackend(Backend):
    def __init__(self, url: str | None = None):
        self.url = (url or os.environ.get("STITCHPROOF_LLAMA_URL", "http://127.0.0.1:8080")).rstrip("/")
        self.name = f"llama.cpp (local, {self.url})"

    def complete(self, messages):
        out = _post(
            f"{self.url}/v1/chat/completions",
            {
                "messages": messages,
                "temperature": 0,
                "max_tokens": 400,
                "chat_template_kwargs": {"enable_thinking": False},
            },
        )
        return out["choices"][0]["message"]["content"] or ""


class OllamaBackend(Backend):
    def __init__(self, model: str | None = None, url: str | None = None):
        self.model = model or os.environ.get("STITCHPROOF_MODEL", "stitchproof")
        self.url = (url or os.environ.get("STITCHPROOF_OLLAMA_URL", "http://127.0.0.1:11434")).rstrip("/")
        self.name = f"Ollama (local, {self.model})"

    def complete(self, messages):
        out = _post(
            f"{self.url}/api/chat",
            {"model": self.model, "messages": messages, "stream": False, "think": False, "options": {"temperature": 0, "num_predict": 400}},
        )
        return out["message"]["content"]


class ReplayBackend(Backend):
    """Demo backend with no model: replays recorded fine-tuned-model answers (data/demo/recorded.jsonl,
    matched on the exact prompt), else gold programs for lines in the synthetic data files."""

    name = "demo: recorded answers from the fine-tuned model"
    concurrency = 1
    is_demo = True
    RECORDED = Path("data/demo/recorded.jsonl")

    def __init__(self, files: list[Path] | None = None, recorded: Path | None = None):
        files = files if files is not None else [Path("data/generated/eval_synth.jsonl"), Path("data/generated/pilot.jsonl"), Path("data/ood/ood.jsonl")]
        self.recorded: dict[str, str] = {}
        rec_path = recorded if recorded is not None else (self.RECORDED if files else None)
        if rec_path is not None and rec_path.exists():
            for row in (json.loads(l) for l in rec_path.read_text().splitlines() if l.strip()):
                self.recorded[row["user"]] = row["output"]
        self.gold: dict[str, str] = {}
        for f in files:
            if f.exists():
                for rec in (json.loads(l) for l in f.read_text().splitlines() if l.strip()):
                    for line in rec["lines"]:
                        self.gold.setdefault(line["text"], to_compact_json(LineProgram.model_validate(line["gold"])))

    def complete(self, messages):
        user = messages[-1]["content"]
        if user in self.recorded:
            return self.recorded[user]
        line = user.split("\nLine: ", 1)[-1]
        return self.gold.get(
            line,
            '{"kind":"unsupported","unsupported_reason":"the online demo only knows its sample patterns; install StitchProof to check your own"}',
        )


class TinkerDemoBackend(Backend):
    """CLOUD DEMO MODE: sends each line to the fine-tuned model on Tinker. Not private."""

    is_local = False
    concurrency = 16

    def __init__(self):
        from ..tinker_io import BASE_MODEL, Sampler

        runs = json.loads(Path("train/runs.json").read_text())
        self.sampler = Sampler(model=BASE_MODEL, model_path=runs["final"]["sampler_path"])
        self.name = "CLOUD DEMO MODE (Tinker): lines are sent to Tinker"

    def complete(self, messages):
        import asyncio

        return asyncio.run(self.sampler.complete(messages))


def get_backend(kind: str | None = None) -> Backend:
    kind = kind or os.environ.get("STITCHPROOF_BACKEND", "llama")
    if kind == "llama":
        return LlamaServerBackend()
    if kind == "ollama":
        return OllamaBackend()
    if kind == "replay":
        return ReplayBackend()
    if kind == "tinker-demo":
        return TinkerDemoBackend()
    raise ValueError(f"unknown backend {kind!r}")


def backend_status(b: Backend) -> tuple[bool, str]:
    """Is the backend reachable? Never sends pattern text."""
    try:
        if isinstance(b, LlamaServerBackend):
            urllib.request.urlopen(f"{b.url}/health", timeout=3)
        elif isinstance(b, OllamaBackend):
            tags = json.loads(urllib.request.urlopen(f"{b.url}/api/tags", timeout=3).read())
            if not any(m["name"].split(":")[0] == b.model.split(":")[0] for m in tags.get("models", [])):
                return False, f"Ollama is running but has no model named {b.model!r}"
        return True, "ready"
    except Exception as e:  # noqa: BLE001
        return False, f"not reachable ({type(e).__name__})"


# ---------------------------------------------------------------------------
# Parsing with a per-line cache
# ---------------------------------------------------------------------------


class LineParser:
    def __init__(self, backend: Backend):
        self.backend = backend
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tag = hashlib.sha1(backend.name.encode()).hexdigest()[:10]
        self.cache_path = CACHE_DIR / f"lines_{tag}.json"
        try:
            self.cache: dict[str, str] = json.loads(self.cache_path.read_text())
        except (OSError, ValueError):
            self.cache = {}

    def _key(self, messages) -> str:
        return hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest()

    def parse(self, items: list[tuple[str, str | None, str]]) -> list[ParseResult]:
        """items: (header, previous line, line). Cached lines are not sent again."""
        msgs = [messages_for_line(h, p, l) for h, p, l in items]
        keys = [self._key(m) for m in msgs]
        todo = [i for i, k in enumerate(keys) if k not in self.cache]
        if todo:
            with ThreadPoolExecutor(max_workers=self.backend.concurrency) as ex:
                outs = list(ex.map(lambda i: self.backend.complete(msgs[i]), todo))
            for i, out in zip(todo, outs):
                self.cache[keys[i]] = out
            self.cache_path.write_text(json.dumps(self.cache))
        return [parse_model_output(self.cache[k]) for k in keys]

    def parse_iter(self, items: list[tuple[str, str | None, str]]):
        """Yield (index, ParseResult) in order, as each line is parsed. Cached lines come first, instantly."""
        msgs = [messages_for_line(h, p, l) for h, p, l in items]
        keys = [self._key(m) for m in msgs]
        try:
            for i, (m, k) in enumerate(zip(msgs, keys)):
                if k not in self.cache:
                    self.cache[k] = self.backend.complete(m)
                yield i, parse_model_output(self.cache[k])
        finally:
            self.cache_path.write_text(json.dumps(self.cache))


@dataclass
class PatternCheck:
    header: str
    lines: list[str]
    parses: list[ParseResult]
    results: list[LineResult]
    backend: str
    counts: dict[str, int] = field(default_factory=dict)


def check_pattern(text: str, parser: LineParser, merge_wrapped: bool = False) -> PatternCheck:
    seg = segment(text, merge_wrapped=merge_wrapped)
    parses = parser.parse([(seg.header, l.prev_text, l.text) for l in seg.lines])
    results = simulate([p.program for p in parses])
    counts: dict[str, int] = {}
    for r in results:
        counts[r.status.value] = counts.get(r.status.value, 0) + 1
    return PatternCheck(seg.header, [l.text for l in seg.lines], parses, results, parser.backend.name, counts)


def check_pattern_iter(text: str, parser: LineParser, merge_wrapped: bool = False):
    """Stream a check: yields ("start", Segmented), then ("line", LineResult) per line, then ("done", PatternCheck).

    Exact, because the simulator is sequential: line i's result depends only on lines up to i,
    so each new line is simulated together with the prefix before it.
    """
    seg = segment(text, merge_wrapped=merge_wrapped)
    yield "start", seg
    parses: list[ParseResult] = []
    for _i, pr in parser.parse_iter([(seg.header, l.prev_text, l.text) for l in seg.lines]):
        parses.append(pr)
        yield "line", simulate([p.program for p in parses])[-1]
    results = simulate([p.program for p in parses])
    counts: dict[str, int] = {}
    for r in results:
        counts[r.status.value] = counts.get(r.status.value, 0) + 1
    yield "done", PatternCheck(seg.header, [l.text for l in seg.lines], parses, results, parser.backend.name, counts)


def check_row(previous_count: int | None, row_text: str, parser: LineParser) -> tuple[str, LineResult | None]:
    row_text = " ".join(row_text.split())
    if not row_text:
        return "Paste one row of the pattern.", None
    parsed = parser.parse([("US terms", None, row_text)])[0]
    if parsed.program is None:
        return "StitchProof couldn't read this row. Try pasting it exactly as the pattern writes it.", None
    return check_single_row(parsed.program, previous_count)
