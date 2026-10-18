import { createSseParser } from "./lib/sse";
import type { ApiError, AppStatus, CheckDone, LineResult, RowAnswer, UploadResult } from "./types";

async function json<T>(r: Response): Promise<T> {
  if (!r.ok) {
    const body = await r.json().catch(() => null);
    const detail = body?.detail;
    throw (typeof detail === "object" && detail?.message ? detail : { message: `Request failed (${r.status}).` }) as ApiError;
  }
  return r.json() as Promise<T>;
}

export function getStatus(): Promise<AppStatus> {
  return fetch("/api/status").then((r) => json<AppStatus>(r));
}

export interface StreamHandlers {
  start: (lines: string[], backend: string) => void;
  line: (line: LineResult) => void;
  done: (done: CheckDone) => void;
  error: (err: ApiError) => void;
}

/** Check a pattern, receiving each row's result as soon as it's parsed. */
export async function streamCheck(text: string, mergeWrapped: boolean, signal: AbortSignal, on: StreamHandlers): Promise<void> {
  let res: Response;
  try {
    res = await fetch("/api/check/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, merge_wrapped: mergeWrapped }),
      signal,
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") return;
    on.error({ message: "StitchProof's local server isn't responding. Is `python -m stitchproof.app.server` still running?" });
    return;
  }
  if (!res.ok || !res.body) {
    on.error(await json(res).then(() => ({ message: "Unexpected response." }), (e: ApiError) => e));
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  const feed = createSseParser();
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      for (const ev of feed(decoder.decode(value, { stream: true }))) {
        if (ev.event === "start") {
          const d = ev.data as { lines: string[]; backend: string };
          on.start(d.lines, d.backend);
        } else if (ev.event === "line") on.line(ev.data as LineResult);
        else if (ev.event === "done") on.done(ev.data as CheckDone);
        else if (ev.event === "error") on.error(ev.data as ApiError);
      }
    }
  } catch (e) {
    if ((e as Error).name !== "AbortError") on.error({ message: "The check was interrupted. Try again." });
  }
}

export async function uploadFile(file: File): Promise<UploadResult> {
  const fd = new FormData();
  fd.append("file", file);
  return fetch("/api/upload", { method: "POST", body: fd }).then((r) => json<UploadResult>(r));
}

export async function checkRow(previousCount: number | null, row: string): Promise<RowAnswer> {
  return fetch("/api/row", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ previous_count: previousCount, row }),
  }).then((r) => json<RowAnswer>(r));
}

export async function downloadReport(text: string, mergeWrapped: boolean, format: "md" | "html"): Promise<void> {
  const r = await fetch(`/api/report?format=${format}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, merge_wrapped: mergeWrapped }),
  });
  if (!r.ok) await json(r);
  const url = URL.createObjectURL(await r.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = `stitchproof_report.${format}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
