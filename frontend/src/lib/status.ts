import type { Status } from "../types";

export interface StatusStyle {
  word: string;
  /** Tailwind classes for text, soft background, left rule. */
  text: string;
  soft: string;
  rule: string;
  /** Screen-reader description. */
  sr: string;
}

export const STATUS: Record<Status, StatusStyle> = {
  OK: { word: "OK", text: "text-ok", soft: "bg-ok-soft", rule: "border-l-transparent", sr: "count matches" },
  ERROR: { word: "Error", text: "text-accent", soft: "bg-accent-soft", rule: "border-l-accent", sr: "stitch count error" },
  WARNING: { word: "Warning", text: "text-warn", soft: "bg-warn-soft", rule: "border-l-warn", sr: "warning" },
  "CAN'T CHECK": { word: "Can't check", text: "text-cant", soft: "bg-cant-soft", rule: "border-l-cant", sr: "can't be checked" },
  NOTE: { word: "Note", text: "text-ink-3", soft: "bg-transparent", rule: "border-l-transparent", sr: "note, not a row" },
};

export const FLAGGED: Status[] = ["ERROR", "WARNING", "CAN'T CHECK"];

export function isFlagged(s: Status | undefined): boolean {
  return !!s && FLAGGED.includes(s);
}

/** "makes 30 · says 31" chip text, or null when there's nothing to compare. */
export function countChip(made: number | null, stated: number | null): string | null {
  if (made == null && stated == null) return null;
  if (stated == null) return `makes ${made}`;
  if (made == null) return `says ${stated}`;
  return made === stated ? `${made}` : `makes ${made} · says ${stated}`;
}
