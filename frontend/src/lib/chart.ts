import type { LineResult, Status } from "../types";

export interface Bar {
  key: string;
  lineIndex: number;
  label: string;
  made: number;
  stated: number | null;
  status: Status;
}

const COUNTED = new Set(["row", "round"]);

/** One bar per worked row; a range like "Rnd 6-9" becomes one bar per round. */
export function silhouetteBars(results: (LineResult | undefined)[]): Bar[] {
  const bars: Bar[] = [];
  for (const r of results) {
    if (!r || !COUNTED.has(r.kind)) continue;
    const values = r.rows_made.length ? r.rows_made : r.made != null ? [r.made] : r.stated != null ? [r.stated] : [];
    const base = r.label ?? `line ${r.index + 1}`;
    values.forEach((made, k) => {
      bars.push({
        key: `${r.index}-${k}`,
        lineIndex: r.index,
        label: values.length > 1 ? `${base} (${k + 1})` : base,
        made,
        stated: r.stated,
        status: r.status,
      });
    });
  }
  return bars;
}

/** "Nice" y-axis ticks from 0 to just above the max (3 to 5 ticks). */
export function niceTicks(max: number): number[] {
  if (max <= 0) return [0];
  const rough = max / 4;
  const pow = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * pow).find((s) => s >= rough) ?? 10 * pow;
  const ticks: number[] = [];
  for (let v = 0; v <= max + step * 0.001; v += step) ticks.push(Math.round(v * 100) / 100);
  if (ticks[ticks.length - 1] < max) ticks.push(Math.round((ticks[ticks.length - 1] + step) * 100) / 100);
  return ticks;
}
