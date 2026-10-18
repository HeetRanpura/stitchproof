"""StitchProof local web app: a small FastAPI server around the check pipeline + the built React UI.

    python -m stitchproof.app.server          # http://127.0.0.1:7860
    stitchproof                               # same, via the console script

Binds to 127.0.0.1 only. Patterns are processed in memory; uploads are read from a temp file
that is deleted straight away; nothing is logged.
"""
from __future__ import annotations

import json
import os
import tempfile
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import photo_reader
from .inputs import InputError, read_file
from .local_model import LineParser, backend_status, check_pattern, check_pattern_iter, check_row, get_backend
from .report_export import summary_line, to_html, to_markdown

WEB = Path(__file__).parent / "web"
HOST = "127.0.0.1"
PORT = int(os.environ.get("STITCHPROOF_PORT", "7860"))
MAX_UPLOAD = 20 * 1024 * 1024
LLAMA_HINT = "llama-server -m models/stitchproof-base-q4_k_m.gguf --lora models/stitchproof-lora-v1.gguf --port 8080 --host 127.0.0.1 --jinja -c 4096 -np 1"


class CheckRequest(BaseModel):
    text: str = Field(max_length=200_000)
    merge_wrapped: bool = False


class RowRequest(BaseModel):
    previous_count: int | None = Field(default=None, ge=0, le=100_000)
    row: str = Field(max_length=5_000)


@lru_cache(maxsize=1)
def parser() -> LineParser:
    return LineParser(get_backend())


def _line(i: int, text: str, r) -> dict:
    d = r.to_dict()
    d["index"] = i
    d["text"] = text
    d["rows_made"] = [row.made for row in r.rows] if r.rows else ([r.made] if r.made is not None else [])
    return d


def _done(check) -> dict:
    return {"counts": check.counts, "summary": summary_line(check), "backend": check.backend, "header": check.header}


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _model_error(e: Exception) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={"message": f"The StitchProof model isn't reachable ({type(e).__name__}). Start it, then try again.", "command": LLAMA_HINT},
    )


app = FastAPI(title="StitchProof", docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/api/status")
def status() -> dict:
    b = parser().backend
    ok, why = backend_status(b)
    if b.is_demo:  # the hosted demo has no Gemma; never upload photos there
        vok, vwhy = False, "only in the installed app"
    else:
        vok, vwhy = photo_reader.status()
    return {
        "model": {"name": b.name, "ready": ok, "detail": why, "local": b.is_local, "demo": b.is_demo, "command": LLAMA_HINT},
        "photo_reader": {"ready": vok, "detail": vwhy, "model": photo_reader.model_name()},
    }


@app.post("/api/check")
def check(req: CheckRequest) -> dict:
    if not req.text.strip():
        raise HTTPException(400, detail={"message": "Paste a pattern first."})
    try:
        c = check_pattern(req.text, parser(), merge_wrapped=req.merge_wrapped)
    except OSError as e:
        raise _model_error(e)
    return {"lines": [_line(i, t, r) for i, (t, r) in enumerate(zip(c.lines, c.results))], **_done(c)}


@app.post("/api/check/stream")
def check_stream(req: CheckRequest) -> StreamingResponse:
    if not req.text.strip():
        raise HTTPException(400, detail={"message": "Paste a pattern first."})

    def events():
        lines: list[str] = []
        try:
            for kind, payload in check_pattern_iter(req.text, parser(), merge_wrapped=req.merge_wrapped):
                if kind == "start":
                    lines = [l.text for l in payload.lines]
                    yield _sse("start", {"header": payload.header, "lines": lines, "backend": parser().backend.name})
                elif kind == "line":
                    yield _sse("line", _line(payload.index, lines[payload.index], payload))
                else:
                    yield _sse("done", _done(payload))
        except OSError as e:
            yield _sse("error", {"message": f"The StitchProof model isn't reachable ({type(e).__name__}). Start it, then try again.", "command": LLAMA_HINT})

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)) -> dict:
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, detail={"message": "That file is larger than 20 MB."})
    suffix = Path(file.filename or "upload").suffix.lower()
    if parser().backend.is_demo and suffix in photo_reader.IMAGE_TYPES:
        raise HTTPException(422, detail={"message": "Photos are read by Gemma 4 on your own computer, so they work only in the installed app."})
    fd, tmp = tempfile.mkstemp(prefix="stitchproof_", suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        text, merge, source = read_file(tmp)
    except InputError as e:
        raise HTTPException(422, detail={"message": str(e)})
    finally:
        Path(tmp).unlink(missing_ok=True)
    return {"text": text, "merge_wrapped": merge, "source": source, "transcribed_by": photo_reader.model_name() if source == "photo" else None}


@app.post("/api/row")
def row(req: RowRequest) -> dict:
    try:
        answer, res = check_row(req.previous_count, req.row, parser())
    except OSError as e:
        raise _model_error(e)
    return {"answer": answer, "result": res.to_dict() if res else None}


@app.post("/api/report")
def report(req: CheckRequest, format: str = "html") -> Response:
    if format not in ("md", "html"):
        raise HTTPException(400, detail={"message": "format must be md or html"})
    try:
        c = check_pattern(req.text, parser(), merge_wrapped=req.merge_wrapped)
    except OSError as e:
        raise _model_error(e)
    if format == "md":
        body, mime = to_markdown(c), "text/markdown; charset=utf-8"
    else:
        body, mime = to_html(c), "text/html; charset=utf-8"
    return Response(body, media_type=mime, headers={"Content-Disposition": f'attachment; filename="stitchproof_report.{format}"'})


@app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "DELETE"])
def api_not_found(rest: str) -> JSONResponse:
    return JSONResponse({"detail": {"message": "Not found"}}, status_code=404)


if (WEB / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=WEB / "assets"), name="assets")


@app.get("/{path:path}", response_model=None)
def spa(path: str) -> FileResponse | HTMLResponse:
    f = (WEB / path).resolve()
    if path and f.is_file() and WEB.resolve() in f.parents:
        return FileResponse(f)
    index = WEB / "index.html"
    if index.exists():
        return FileResponse(index)
    return HTMLResponse("<p>The StitchProof web UI isn't built. Run <code>npm --prefix frontend run build</code>.</p>", status_code=503)


def main() -> None:
    import uvicorn

    print(f"StitchProof: http://{HOST}:{PORT}  (local only)")
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
