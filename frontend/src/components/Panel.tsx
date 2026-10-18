import { DownloadSimpleIcon } from "@phosphor-icons/react";
import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import { isFlagged, STATUS } from "../lib/status";
import type { Counts, LineResult } from "../types";
import { RowBadge } from "./RowBadge";
import { Silhouette } from "./Silhouette";

function Metric({ value, label, tone, pending }: { value: number; label: string; tone: string; pending: boolean }) {
  return (
    <div className="min-w-0">
      {pending ? (
        <div className="shimmer h-10 w-12 rounded" />
      ) : (
        <p className={`num font-display text-[2.6rem] leading-none font-light tracking-tight ${tone}`} style={{ fontVariationSettings: '"opsz" 144' }}>
          {value}
        </p>
      )}
      <p className="mt-2 font-mono text-[11px] tracking-[0.14em] text-ink-3 uppercase">{label}</p>
    </div>
  );
}

export function MetricsStrip({ counts, rows, pending }: { counts: Counts; rows: number; pending: boolean }) {
  const errors = counts.ERROR ?? 0;
  return (
    <section aria-label="Summary" className="grid grid-cols-4 gap-4 border-b border-rule pb-6" aria-live="polite">
      <Metric value={rows} label="rows" tone="text-ink" pending={pending} />
      <Metric value={errors} label={errors === 1 ? "error" : "errors"} tone={errors ? "text-accent" : "text-ink"} pending={pending} />
      <Metric value={counts.WARNING ?? 0} label="warnings" tone="text-ink" pending={pending} />
      <Metric value={counts["CAN'T CHECK"] ?? 0} label="can't check" tone="text-ink" pending={pending} />
    </section>
  );
}

function Numbers({ r }: { r: LineResult }) {
  const cells: [string, number | null][] = [
    ["available", r.available],
    ["used", r.used],
    ["made", r.made],
    ["stated", r.stated],
  ];
  return (
    <dl className="mt-4 grid grid-cols-4 overflow-hidden rounded-lg border border-rule">
      {cells.map(([k, v], i) => (
        <div key={k} className={`px-3 py-2.5 ${i ? "border-l border-rule" : ""} ${k === "made" && r.status === "ERROR" ? "bg-accent-soft" : ""}`}>
          <dt className="font-mono text-[10px] tracking-[0.12em] text-ink-3 uppercase">{k}</dt>
          <dd className={`num mt-1 font-mono text-[18px] ${k === "made" && r.status === "ERROR" ? "text-accent" : "text-ink"}`}>{v ?? "–"}</dd>
        </div>
      ))}
    </dl>
  );
}

export function RowDetail({ r, checking }: { r: LineResult | undefined; checking: boolean }) {
  return (
    <section aria-label="Selected row" className="border-b border-rule py-6">
      <AnimatePresence mode="wait" initial={false}>
        {r ? (
          <motion.div
            key={r.index}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
          >
            <div className="flex items-center justify-between gap-3">
              <h3 className="font-display text-[1.35rem] leading-tight text-ink">{r.label ?? `Line ${r.index + 1}`}</h3>
              <RowBadge status={r.status} />
            </div>
            <p className="mt-3 font-serif text-[16px] leading-relaxed text-ink">{r.explanation}</p>
            {r.status !== "NOTE" && r.kind !== "unsupported" && <Numbers r={r} />}
            <div className="mt-4 grid gap-1.5 text-[13px]">
              <p className="text-ink-2">
                <span className="font-mono text-[11px] tracking-[0.12em] text-ink-3 uppercase">read as </span>
                <span className="font-mono text-ink">{r.program_text}</span>
              </p>
              {r.codes.length > 0 && (
                <p className="font-mono text-[11px] tracking-[0.08em] text-ink-3">{r.codes.join(" · ")}</p>
              )}
            </div>
          </motion.div>
        ) : (
          <motion.p key="none" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="font-serif text-[15px] leading-relaxed text-ink-3 italic">
            {checking ? "Rows appear here as they're checked. Select any row to see its numbers." : "Select a row to see how its count was worked out."}
          </motion.p>
        )}
      </AnimatePresence>
    </section>
  );
}

export function FlaggedList({ results, selected, onSelect }: { results: (LineResult | undefined)[]; selected: number | null; onSelect: (i: number) => void }) {
  const flagged = results.filter((r): r is LineResult => !!r && isFlagged(r.status));
  if (!flagged.length) return null;
  return (
    <section aria-labelledby="flagged-title" className="border-b border-rule py-6">
      <h3 id="flagged-title" className="font-mono text-[11px] tracking-[0.16em] text-ink-3 uppercase">
        Rows to look at
      </h3>
      <ul className="mt-3 grid gap-1">
        {flagged.map((r) => (
          <li key={r.index}>
            <button
              type="button"
              onClick={() => onSelect(r.index)}
              aria-current={selected === r.index ? "true" : undefined}
              className={`press flex min-h-11 w-full cursor-pointer items-center gap-3 rounded-lg px-3 text-left hover:bg-card-2 ${selected === r.index ? "bg-card-2" : ""}`}
            >
              <RowBadge status={r.status} compact />
              <span className="min-w-0 flex-1 truncate text-[14px] text-ink">{r.label ?? r.text}</span>
              <span className={`text-[12px] ${STATUS[r.status].text}`}>{STATUS[r.status].word}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function ReportButtons({ onDownload, disabled }: { onDownload: (f: "md" | "html") => Promise<void>; disabled: boolean }) {
  const [busy, setBusy] = useState<"md" | "html" | null>(null);
  const [err, setErr] = useState<string | null>(null);
  async function go(f: "md" | "html") {
    setBusy(f);
    setErr(null);
    try {
      await onDownload(f);
    } catch (e) {
      setErr((e as { message?: string }).message ?? "Couldn't make the report.");
    } finally {
      setBusy(null);
    }
  }
  return (
    <section aria-label="Reports" className="py-6">
      <h3 className="font-mono text-[11px] tracking-[0.16em] text-ink-3 uppercase">Report</h3>
      <div className="mt-3 flex flex-wrap gap-2">
        {(["html", "md"] as const).map((f) => (
          <button
            key={f}
            type="button"
            disabled={disabled || busy !== null}
            onClick={() => go(f)}
            className="press inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-lg border border-rule-strong bg-card px-4 text-[14px] font-medium text-ink hover:bg-card-2 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <DownloadSimpleIcon size={16} aria-hidden="true" />
            {busy === f ? "Preparing…" : f === "html" ? "Download HTML" : "Download Markdown"}
          </button>
        ))}
      </div>
      {err && <p className="mt-2 text-[13px] text-accent">{err}</p>}
    </section>
  );
}

export function Panel(props: {
  results: (LineResult | undefined)[];
  counts: Counts;
  rows: number;
  checking: boolean;
  selected: number | null;
  onSelect: (i: number) => void;
  onDownload: (f: "md" | "html") => Promise<void>;
}) {
  const r = props.selected != null ? props.results[props.selected] : undefined;
  return (
    <aside className="sheet px-5 py-6 sm:px-6 lg:sticky lg:top-6" aria-label="Results">
      <MetricsStrip counts={props.counts} rows={props.rows} pending={props.checking && props.rows === 0} />
      <RowDetail r={r} checking={props.checking} />
      <FlaggedList results={props.results} selected={props.selected} onSelect={props.onSelect} />
      <Silhouette results={props.results} selected={props.selected} onSelect={props.onSelect} />
      <ReportButtons onDownload={props.onDownload} disabled={props.checking} />
    </aside>
  );
}
