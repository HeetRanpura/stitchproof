import { CameraIcon, PencilSimpleIcon, SpinnerIcon, StopIcon, UploadSimpleIcon } from "@phosphor-icons/react";
import { useRef, useState } from "react";
import type { ApiError, LineResult } from "../types";
import { AnnotatedRows } from "./AnnotatedRows";
import { EmptyState } from "./EmptyState";
import { PhotoFrame } from "./PhotoReview";
import { ServerBanner } from "./ServerBanner";

export type Phase = "empty" | "edit" | "reading" | "checking" | "review";

interface Props {
  phase: Phase;
  text: string;
  onText: (t: string) => void;
  lines: string[];
  results: (LineResult | undefined)[];
  selected: number | null;
  onSelect: (i: number) => void;
  onCheck: () => void;
  onCancel: () => void;
  onEdit: () => void;
  onExample: () => void;
  onFile: (f: File) => void;
  onStartTyping: () => void;
  photo: { url: string; model: string } | null;
  photoReady: boolean;
  photoDetail: string;
  error: ApiError | null;
  onDismissError: () => void;
  readingWhat: string;
}

const ACCEPT_FILES = ".txt,.md,.markdown,.pdf";
const ACCEPT_PHOTOS = "image/png,image/jpeg,image/webp";

export function PatternSheet(p: Props) {
  const fileInput = useRef<HTMLInputElement>(null);
  const photoInput = useRef<HTMLInputElement>(null);
  const editor = useRef<HTMLTextAreaElement>(null);
  const [dragging, setDragging] = useState(false);
  const done = p.results.filter(Boolean).length;
  const busy = p.phase === "checking" || p.phase === "reading";

  function pick(input: HTMLInputElement | null) {
    input?.click();
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files?.[0];
    if (f) p.onFile(f);
  }

  const hidden = (
    <>
      <input ref={fileInput} type="file" accept={ACCEPT_FILES} className="sr-only" tabIndex={-1} aria-hidden="true" onChange={(e) => e.target.files?.[0] && p.onFile(e.target.files[0])} />
      <input ref={photoInput} type="file" accept={ACCEPT_PHOTOS} className="sr-only" tabIndex={-1} aria-hidden="true" onChange={(e) => e.target.files?.[0] && p.onFile(e.target.files[0])} />
    </>
  );

  return (
    <section
      aria-labelledby="sheet-title"
      className={`sheet relative overflow-hidden transition-colors ${dragging ? "ring-2 ring-accent ring-offset-4 ring-offset-paper" : ""}`}
      onDragOver={(e) => {
        e.preventDefault();
        if (!busy) setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => !busy && onDrop(e)}
    >
      <h2 id="sheet-title" className="sr-only">
        Your pattern
      </h2>
      {hidden}
      {p.error && <ServerBanner error={p.error} onRetry={p.error.command ? p.onCheck : undefined} onDismiss={p.onDismissError} />}

      {p.phase === "empty" ? (
        <EmptyState
          onPaste={() => {
            p.onStartTyping();
            setTimeout(() => editor.current?.focus(), 30);
          }}
          onFile={() => pick(fileInput.current)}
          onPhoto={() => pick(photoInput.current)}
          onExample={p.onExample}
          photoReady={p.photoReady}
          photoDetail={p.photoDetail}
        />
      ) : (
        <>
          {/* toolbar */}
          <div className="flex flex-wrap items-center gap-2 border-b border-rule px-4 py-3 sm:px-5">
            {p.phase === "review" ? (
              <button type="button" onClick={p.onEdit} className="press inline-flex min-h-10 cursor-pointer items-center gap-2 rounded-lg border border-rule-strong bg-card px-3.5 text-[14px] font-medium text-ink hover:bg-card-2">
                <PencilSimpleIcon size={16} aria-hidden="true" /> Edit pattern
              </button>
            ) : (
              <>
                <button type="button" disabled={busy} onClick={() => pick(fileInput.current)} className="press inline-flex min-h-10 cursor-pointer items-center gap-2 rounded-lg px-3 text-[14px] text-ink-2 hover:bg-card-2 hover:text-ink disabled:cursor-not-allowed disabled:opacity-50">
                  <UploadSimpleIcon size={16} aria-hidden="true" /> Open file
                </button>
                <button
                  type="button"
                  disabled={busy || !p.photoReady}
                  title={p.photoReady ? "Transcribe a photo with Gemma 4 on this computer" : p.photoDetail}
                  onClick={() => pick(photoInput.current)}
                  className="press inline-flex min-h-10 cursor-pointer items-center gap-2 rounded-lg px-3 text-[14px] text-ink-2 hover:bg-card-2 hover:text-ink disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <CameraIcon size={16} aria-hidden="true" /> Photo
                </button>
              </>
            )}
            <div className="ml-auto flex items-center gap-3">
              {p.phase === "checking" && (
                <span className="hidden font-mono text-[12px] text-ink-3 sm:inline" aria-live="polite">
                  reading row {Math.min(done + 1, p.lines.length)} of {p.lines.length}
                </span>
              )}
              {p.phase === "checking" ? (
                <button type="button" onClick={p.onCancel} className="press inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-lg border border-rule-strong px-4 text-[14px] font-medium text-ink">
                  <StopIcon size={15} aria-hidden="true" /> Stop
                </button>
              ) : p.phase !== "review" ? (
                <button
                  type="button"
                  onClick={p.onCheck}
                  disabled={busy || !p.text.trim()}
                  className="press inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-lg bg-accent px-5 text-[15px] font-semibold text-accent-ink shadow-[0_8px_18px_-10px_var(--accent)] hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Check stitch counts
                </button>
              ) : null}
            </div>
          </div>

          {/* body */}
          {p.phase === "reading" ? (
            <div className="px-6 py-10" aria-live="polite">
              <p className="flex items-center gap-2 text-[15px] text-ink-2">
                <SpinnerIcon size={18} className="animate-spin text-accent motion-reduce:animate-none" aria-hidden="true" />
                {p.readingWhat}
              </p>
              <div className="mt-6 grid gap-3">
                {[92, 76, 84, 60, 88, 70].map((w, i) => (
                  <div key={i} className="shimmer h-4 rounded" style={{ width: `${w}%` }} />
                ))}
              </div>
            </div>
          ) : p.phase === "edit" ? (
            <div className={p.photo ? "grid gap-8 p-5 md:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] md:p-6" : ""}>
              {p.photo && <PhotoFrame url={p.photo.url} model={p.photo.model} />}
              <label className="block">
                <span className="sr-only">Pattern text</span>
                <textarea
                  ref={editor}
                  value={p.text}
                  onChange={(e) => p.onText(e.target.value)}
                  spellCheck={false}
                  placeholder={"Rnd 1: 6 sc in MR (6)\nRnd 2: inc x6 (12)\n…"}
                  className={`ruled block min-h-[26rem] w-full resize-y bg-transparent font-serif text-[17px] text-ink placeholder:text-ink-3 focus:outline-none ${
                    p.photo ? "rounded-lg border border-rule px-4" : "px-6 sm:px-8"
                  }`}
                  style={{ paddingTop: "calc(var(--row) * 0.5)", paddingBottom: "var(--row)" }}
                />
              </label>
            </div>
          ) : (
            <AnnotatedRows lines={p.lines} results={p.results} selected={p.selected} onSelect={p.onSelect} />
          )}
          <p className="border-t border-rule px-5 py-3 text-[12px] text-ink-3">
            Drop a .txt, .md, .pdf or a photo anywhere on this sheet.
          </p>
        </>
      )}
      {dragging && (
        <div className="pointer-events-none absolute inset-0 grid place-items-center bg-card/85 backdrop-blur-[1px]">
          <p className="font-display text-xl text-ink">Drop to open it here</p>
        </div>
      )}
    </section>
  );
}
