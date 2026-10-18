import { motion } from "motion/react";
import { useEffect, useRef } from "react";
import { countChip, STATUS } from "../lib/status";
import type { LineResult } from "../types";
import { RowBadge } from "./RowBadge";

interface Props {
  lines: string[];
  results: (LineResult | undefined)[];
  selected: number | null;
  onSelect: (i: number) => void;
}

/** The pattern itself, each row annotated in place like a spellchecker. */
export function AnnotatedRows({ lines, results, selected, onSelect }: Props) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  useEffect(() => {
    if (selected != null) refs.current[selected]?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [selected]);

  function onKey(e: React.KeyboardEvent, i: number) {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    e.preventDefault();
    const step = e.key === "ArrowDown" ? 1 : -1;
    for (let j = i + step; j >= 0 && j < lines.length; j += step) {
      if (results[j]?.status !== "NOTE") {
        onSelect(j);
        refs.current[j]?.focus();
        return;
      }
    }
  }

  return (
    <ol className="divide-y divide-rule" aria-label="Pattern rows">
      {lines.map((text, i) => {
        const r = results[i];
        const isNote = r?.status === "NOTE";
        const isError = r?.status === "ERROR";
        const chip = r && !isNote ? countChip(r.made, r.stated) : null;
        const isSel = selected === i;
        return (
          <li key={i} className="relative">
            {isSel && (
              <motion.span
                layoutId="row-highlight"
                className="absolute inset-0 bg-card-2"
                transition={{ type: "spring", stiffness: 380, damping: 34 }}
                aria-hidden="true"
              />
            )}
            <button
              ref={(el) => {
                refs.current[i] = el;
              }}
              type="button"
              onClick={() => onSelect(i)}
              onKeyDown={(e) => onKey(e, i)}
              aria-current={isSel ? "true" : undefined}
              aria-label={`${text}. ${r ? STATUS[r.status].sr : "checking"}${chip ? `, ${chip}` : ""}`}
              className={`relative grid w-full cursor-pointer grid-cols-[2.25rem_1fr] gap-x-3 border-l-[3px] px-3 py-2.5 text-left sm:grid-cols-[2.25rem_7rem_1fr_auto] sm:items-center sm:px-4 ${
                r ? STATUS[r.status].rule : "border-l-transparent"
              }`}
            >
              <span className="num pt-1 font-mono text-[12px] text-ink-3 sm:pt-0">{String(i + 1).padStart(2, "0")}</span>
              <span className="hidden sm:block">
                <motion.span
                  key={r?.status ?? "pending"}
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ type: "spring", stiffness: 260, damping: 24 }}
                  className="inline-block"
                >
                  {!isNote && <RowBadge status={r?.status} />}
                </motion.span>
              </span>
              <span
                className={`col-start-2 font-serif text-[17px] leading-relaxed sm:col-start-3 ${
                  isNote ? "text-ink-3 italic" : "text-ink"
                }`}
              >
                <span className={isError ? "wavy-error" : ""}>{text}</span>
                <span className="mt-1 flex items-center gap-2 sm:hidden">
                  {!isNote && <RowBadge status={r?.status} />}
                  {chip && <span className="num font-mono text-[12px] text-ink-2">{chip}</span>}
                </span>
              </span>
              <span className="hidden sm:block">
                {chip && (
                  <span
                    className={`num rounded-full px-2.5 py-1 font-mono text-[12px] whitespace-nowrap ${
                      isError ? "bg-accent-soft text-accent" : "text-ink-2"
                    }`}
                  >
                    {chip}
                  </span>
                )}
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}
