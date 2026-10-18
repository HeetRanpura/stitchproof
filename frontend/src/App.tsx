import { LockSimpleIcon } from "@phosphor-icons/react";
import { MotionConfig } from "motion/react";
import { useCallback, useEffect, useRef, useState } from "react";
import { downloadReport, getStatus, streamCheck, uploadFile } from "./api";
import { Masthead, type Mode } from "./components/Masthead";
import { MakerPanel } from "./components/MakerPanel";
import { Panel } from "./components/Panel";
import { PatternSheet, type Phase } from "./components/PatternSheet";
import { EXAMPLE } from "./lib/example";
import { isFlagged } from "./lib/status";
import type { ApiError, AppStatus, Counts, LineResult } from "./types";

export default function App() {
  const [mode, setMode] = useState<Mode>("check");
  const [status, setStatus] = useState<AppStatus | null>(null);
  const [phase, setPhase] = useState<Phase>("empty");
  const [text, setText] = useState("");
  const [mergeWrapped, setMergeWrapped] = useState(false);
  const [lines, setLines] = useState<string[]>([]);
  const [results, setResults] = useState<(LineResult | undefined)[]>([]);
  const [counts, setCounts] = useState<Counts>({});
  const [selected, setSelected] = useState<number | null>(null);
  const [photo, setPhoto] = useState<{ url: string; model: string } | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [readingWhat, setReadingWhat] = useState("");
  const abort = useRef<AbortController | null>(null);

  const refreshStatus = useCallback(() => {
    getStatus().then(setStatus, () =>
      setStatus({
        model: { name: "local server", ready: false, detail: "not responding", local: true, command: "" },
        photo_reader: { ready: false, detail: "local server not responding", model: "" },
      }),
    );
  }, []);

  useEffect(() => {
    refreshStatus();
    const t = setInterval(refreshStatus, 20000);
    return () => clearInterval(t);
  }, [refreshStatus]);

  const runCheck = useCallback(
    async (source?: string) => {
      const body = source ?? text;
      if (!body.trim()) return;
      abort.current?.abort();
      const ctl = new AbortController();
      abort.current = ctl;
      setError(null);
      setPhase("checking");
      setResults([]);
      setCounts({});
      setSelected(null);
      let firstFlag: number | null = null;
      await streamCheck(body, mergeWrapped, ctl.signal, {
        start: (ls) => {
          setLines(ls);
          setResults(new Array(ls.length).fill(undefined));
        },
        line: (r) => {
          setResults((prev) => {
            const next = prev.slice();
            next[r.index] = r;
            return next;
          });
          setCounts((c) => ({ ...c, [r.status]: (c[r.status] ?? 0) + 1 }));
          if (firstFlag === null && isFlagged(r.status) && r.status === "ERROR") {
            firstFlag = r.index;
            setSelected(r.index);
          }
        },
        done: (d) => {
          setCounts(d.counts);
          setPhase("review");
        },
        error: (e) => {
          setError(e);
          setPhase("edit");
          refreshStatus();
        },
      });
      if (ctl.signal.aborted) setPhase("edit");
    },
    [text, mergeWrapped, refreshStatus],
  );

  function cancel() {
    abort.current?.abort();
    setPhase("edit");
  }

  async function openFile(f: File) {
    setError(null);
    const isPhoto = f.type.startsWith("image/");
    setReadingWhat(isPhoto ? `Gemma 4 is reading your photo on this computer. This takes about half a minute.` : `Reading ${f.name}…`);
    setPhase("reading");
    try {
      const res = await uploadFile(f);
      if (photo) URL.revokeObjectURL(photo.url);
      setPhoto(res.source === "photo" ? { url: URL.createObjectURL(f), model: res.transcribed_by ?? "Gemma 4" } : null);
      setText(res.text);
      setMergeWrapped(res.merge_wrapped);
      setPhase("edit");
    } catch (e) {
      setError(e as ApiError);
      setPhase(text.trim() ? "edit" : "empty");
    }
  }

  function tryExample() {
    setPhoto(null);
    setText(EXAMPLE);
    setMergeWrapped(false);
    runCheck(EXAMPLE);
  }

  const rows = results.filter((r) => r && r.status !== "NOTE").length;
  const showPanel = phase === "checking" || phase === "review";

  return (
    <MotionConfig reducedMotion="user">
      <div className="grain" aria-hidden="true" />
      <a href="#main" className="sr-only z-50 rounded-md bg-ink px-3 py-2 text-paper focus:not-sr-only focus:fixed focus:top-3 focus:left-3">
        Skip to the pattern
      </a>
      <div className="relative z-10 mx-auto flex min-h-[100dvh] max-w-[1400px] flex-col px-4 sm:px-6 lg:px-10">
        <Masthead status={status} mode={mode} onMode={setMode} />
        <main id="main" className="mt-8 flex-1 md:mt-10">
          {mode === "row" ? (
            <MakerPanel />
          ) : (
            <div className={`grid items-start gap-6 ${showPanel ? "lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]" : ""}`}>
              <PatternSheet
                phase={phase}
                text={text}
                onText={setText}
                lines={lines}
                results={results}
                selected={selected}
                onSelect={setSelected}
                onCheck={() => runCheck()}
                onCancel={cancel}
                onEdit={() => setPhase("edit")}
                onExample={tryExample}
                onFile={openFile}
                onStartTyping={() => setPhase("edit")}
                photo={photo}
                photoReady={!!status?.photo_reader.ready}
                photoDetail={status?.photo_reader.detail ?? "checking"}
                error={error}
                onDismissError={() => setError(null)}
                readingWhat={readingWhat}
              />
              {showPanel && (
                <Panel
                  results={results}
                  counts={counts}
                  rows={rows}
                  checking={phase === "checking"}
                  selected={selected}
                  onSelect={setSelected}
                  onDownload={(f) => downloadReport(text, mergeWrapped, f)}
                />
              )}
            </div>
          )}
        </main>
        <footer className="mt-12 flex flex-col gap-2 border-t border-rule py-6 text-[13px] text-ink-2 sm:flex-row sm:items-center sm:justify-between">
          <p className="inline-flex items-center gap-2">
            <LockSimpleIcon size={15} className="text-ok" aria-hidden="true" />
            Runs on your computer. Your pattern never leaves it.
          </p>
          <p className="text-ink-3">StitchProof checks stitch math only, not gauge, sizing or shape.</p>
        </footer>
      </div>
    </MotionConfig>
  );
}
