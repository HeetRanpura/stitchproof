import { useMemo, useState } from "react";
import { niceTicks, silhouetteBars, type Bar } from "../lib/chart";
import { STATUS } from "../lib/status";
import type { LineResult } from "../types";

const W = 360;
const H = 170;
const PAD = { l: 30, r: 6, t: 18, b: 22 };

/** Stitches made per row. For amigurumi it traces the outline of the piece, so a mistake shows as a dent. */
export function Silhouette({ results, selected, onSelect }: { results: (LineResult | undefined)[]; selected: number | null; onSelect: (i: number) => void }) {
  const bars = useMemo(() => silhouetteBars(results), [results]);
  const [hover, setHover] = useState<Bar | null>(null);
  if (bars.length < 2) return null;

  const max = Math.max(...bars.map((b) => Math.max(b.made, b.stated ?? 0)));
  const ticks = niceTicks(max);
  const top = ticks[ticks.length - 1] || 1;
  const iw = W - PAD.l - PAD.r;
  const ih = H - PAD.t - PAD.b;
  const step = iw / bars.length;
  const bw = Math.max(2, Math.min(18, step - 2));
  const y = (v: number) => PAD.t + ih - (v / top) * ih;
  const errors = bars.filter((b) => b.status === "ERROR");
  const summary = `Stitches made per row, from ${bars[0].made} to a peak of ${Math.max(...bars.map((b) => b.made))}. ${
    errors.length ? `${errors.length} bar${errors.length > 1 ? "s" : ""} marked as errors: ${errors.map((b) => b.label).join(", ")}.` : "No errors."
  }`;

  return (
    <section aria-labelledby="sil-title" className="border-b border-rule py-6">
      <div className="flex items-baseline justify-between">
        <h3 id="sil-title" className="font-mono text-[11px] tracking-[0.16em] text-ink-3 uppercase">
          Silhouette
        </h3>
        <p className="text-[12px] text-ink-3">stitches per row</p>
      </div>
      <p className="sr-only">{summary}</p>
      <div className="relative mt-3">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full overflow-visible" role="group" aria-label="Silhouette chart">
          <defs>
            <pattern id="hatch-err" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <rect width="5" height="5" className="fill-accent" />
              <line x1="0" y1="0" x2="0" y2="5" className="stroke-accent-soft" strokeWidth="1.6" />
            </pattern>
            <pattern id="hatch-cant" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(-45)">
              <rect width="5" height="5" className="fill-cant-soft" />
              <line x1="0" y1="0" x2="0" y2="5" className="stroke-cant" strokeWidth="1.2" />
            </pattern>
          </defs>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={PAD.l} x2={W - PAD.r} y1={y(t)} y2={y(t)} className="stroke-rule" strokeWidth="1" />
              <text x={PAD.l - 6} y={y(t) + 3.5} textAnchor="end" className="num fill-ink-3 font-mono text-[9px]">
                {t}
              </text>
            </g>
          ))}
          {bars.map((b, i) => {
            const x = PAD.l + i * step + (step - bw) / 2;
            const h = Math.max(1, y(0) - y(b.made));
            const isSel = selected === b.lineIndex;
            const fill =
              b.status === "ERROR" ? "url(#hatch-err)" : b.status === "CAN'T CHECK" ? "url(#hatch-cant)" : undefined;
            return (
              <g
                key={b.key}
                tabIndex={0}
                role="button"
                aria-label={`${b.label}: makes ${b.made}${b.stated != null ? `, says ${b.stated}` : ""}, ${STATUS[b.status].word}`}
                onClick={() => onSelect(b.lineIndex)}
                onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onSelect(b.lineIndex)}
                onMouseEnter={() => setHover(b)}
                onMouseLeave={() => setHover(null)}
                onFocus={() => setHover(b)}
                onBlur={() => setHover(null)}
                className="cursor-pointer outline-none"
              >
                <rect x={PAD.l + i * step} y={PAD.t} width={step} height={ih} fill="transparent" />
                <rect
                  x={x}
                  y={y(b.made)}
                  width={bw}
                  height={h}
                  rx={Math.min(3, bw / 3)}
                  fill={fill}
                  className={`${fill ? "" : b.status === "WARNING" ? "fill-warn" : "fill-ok"} transition-opacity ${
                    selected != null && !isSel ? "opacity-55" : ""
                  }`}
                />
                {isSel && <rect x={x - 2} y={y(b.made) - 2} width={bw + 4} height={h + 4} rx="4" fill="none" className="stroke-ink" strokeWidth="1.2" />}
                {b.status === "ERROR" && (
                  <text x={x + bw / 2} y={y(b.made) - 5} textAnchor="middle" className="fill-accent font-mono text-[8px] font-semibold tracking-wider">
                    ERROR
                  </text>
                )}
              </g>
            );
          })}
          <line x1={PAD.l} x2={W - PAD.r} y1={y(0)} y2={y(0)} className="stroke-rule-strong" strokeWidth="1" />
          <text x={PAD.l} y={H - 6} className="fill-ink-3 font-mono text-[9px]">
            {bars[0].label}
          </text>
          <text x={W - PAD.r} y={H - 6} textAnchor="end" className="fill-ink-3 font-mono text-[9px]">
            {bars[bars.length - 1].label}
          </text>
        </svg>
        {hover && (
          <div
            className="pointer-events-none absolute -top-2 z-10 -translate-x-1/2 -translate-y-full rounded-md border border-rule bg-card px-2.5 py-1.5 text-[12px] whitespace-nowrap text-ink shadow-[0_10px_24px_-14px_rgb(var(--shadow)/0.5)]"
            style={{ left: `${((PAD.l + (bars.indexOf(hover) + 0.5) * step) / W) * 100}%` }}
            role="status"
          >
            <span className="font-medium">{hover.label}</span>
            <span className="num ml-2 font-mono text-ink-2">
              makes {hover.made}
              {hover.stated != null && hover.stated !== hover.made ? ` · says ${hover.stated}` : ""}
            </span>
            <span className={`ml-2 ${STATUS[hover.status].text}`}>{STATUS[hover.status].word}</span>
          </div>
        )}
      </div>
      <p className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-ink-2">
        <span className="inline-flex items-center gap-1.5">
          <span className="size-2.5 rounded-sm bg-ok" aria-hidden="true" /> matches
        </span>
        <span className="inline-flex items-center gap-1.5">
          <svg width="10" height="10" aria-hidden="true">
            <rect width="10" height="10" rx="2" fill="url(#hatch-err)" />
          </svg>
          error
        </span>
        <span className="inline-flex items-center gap-1.5">
          <svg width="10" height="10" aria-hidden="true">
            <rect width="10" height="10" rx="2" fill="url(#hatch-cant)" />
          </svg>
          can't check
        </span>
      </p>
    </section>
  );
}
