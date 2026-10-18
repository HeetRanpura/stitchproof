import { CheckCircleIcon, NotePencilIcon, QuestionIcon, WarningCircleIcon, XCircleIcon } from "@phosphor-icons/react";
import { STATUS } from "../lib/status";
import type { Status } from "../types";

const ICONS = {
  OK: CheckCircleIcon,
  ERROR: XCircleIcon,
  WARNING: WarningCircleIcon,
  "CAN'T CHECK": QuestionIcon,
  NOTE: NotePencilIcon,
} as const;

/** Icon + word, so status never depends on colour alone. */
export function RowBadge({ status, compact = false }: { status: Status | undefined; compact?: boolean }) {
  if (!status) {
    return <span className="shimmer inline-block h-5 w-[4.5rem] rounded-full" aria-label="checking" />;
  }
  const s = STATUS[status];
  const Icon = ICONS[status];
  return (
    <span className={`inline-flex items-center gap-1.5 text-[12px] font-medium tracking-wide ${s.text}`}>
      <Icon size={16} weight={status === "ERROR" ? "fill" : "regular"} aria-hidden="true" />
      <span className={compact ? "sr-only" : "uppercase"}>{s.word}</span>
    </span>
  );
}
