import { ArrowClockwiseIcon, WarningCircleIcon } from "@phosphor-icons/react";
import type { ApiError } from "../types";

/** Inline error with a way out: what happened, the command that fixes it, and Retry. */
export function ServerBanner({ error, onRetry, onDismiss }: { error: ApiError; onRetry?: () => void; onDismiss: () => void }) {
  return (
    <div role="alert" className="flex flex-col gap-3 border-b border-rule bg-warn-soft px-5 py-4 sm:flex-row sm:items-start">
      <WarningCircleIcon size={20} className="mt-0.5 shrink-0 text-warn" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="text-[14px] font-medium text-ink">{error.message}</p>
        {error.command && (
          <>
            <p className="mt-2 text-[13px] text-ink-2">Start the local model in a terminal:</p>
            <code className="mt-1 block overflow-x-auto rounded-md bg-card px-3 py-2 font-mono text-[12px] whitespace-pre text-ink">{error.command}</code>
          </>
        )}
      </div>
      <div className="flex gap-2">
        {onRetry && (
          <button type="button" onClick={onRetry} className="press inline-flex min-h-10 cursor-pointer items-center gap-1.5 rounded-lg border border-rule-strong bg-card px-3 text-[13px] font-medium text-ink">
            <ArrowClockwiseIcon size={15} aria-hidden="true" /> Retry
          </button>
        )}
        <button type="button" onClick={onDismiss} className="press min-h-10 cursor-pointer rounded-lg px-3 text-[13px] text-ink-2 hover:text-ink">
          Dismiss
        </button>
      </div>
    </div>
  );
}
