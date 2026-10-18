import { CheckCircleIcon, QuestionIcon, XCircleIcon } from "@phosphor-icons/react";
import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import { checkRow } from "../api";
import type { ApiError, RowAnswer } from "../types";
import { ServerBanner } from "./ServerBanner";

/** "Is the pattern wrong, or am I?" One row, a known previous count, a one-sentence answer. */
export function MakerPanel() {
  const [prev, setPrev] = useState("24");
  const [row, setRow] = useState("Rnd 5: (sc 3, inc) x6 (31)");
  const [answer, setAnswer] = useState<RowAnswer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const prevNum = prev.trim() === "" ? null : Number(prev);
  const prevInvalid = prevNum !== null && (!Number.isInteger(prevNum) || prevNum < 0);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (prevInvalid || !row.trim()) return;
    setBusy(true);
    setError(null);
    try {
      setAnswer(await checkRow(prevNum, row));
    } catch (err) {
      setError(err as ApiError);
    } finally {
      setBusy(false);
    }
  }

  const status = answer?.result?.status;
  const Verdict = status === "ERROR" ? XCircleIcon : status === "OK" ? CheckCircleIcon : QuestionIcon;
  const tone = status === "ERROR" ? "text-accent" : status === "OK" ? "text-ok" : "text-ink-2";

  return (
    <div className="grid gap-6 lg:grid-cols-[7fr_5fr]">
      <form onSubmit={submit} className="sheet overflow-hidden" aria-labelledby="maker-title">
        {error && <ServerBanner error={error} onDismiss={() => setError(null)} />}
        <div className="px-6 py-8 sm:px-8">
          <p className="font-mono text-[11px] tracking-[0.18em] text-ink-3 uppercase">Mid-project</p>
          <h2 id="maker-title" className="mt-3 font-display text-[1.9rem] leading-tight tracking-tight text-ink">
            Is the pattern wrong, or am I?
          </h2>
          <p className="mt-3 max-w-[48ch] font-serif text-[16px] leading-relaxed text-ink-2">
            Count the stitches you had at the end of the previous row, then paste the row you're stuck on exactly as the pattern writes it.
          </p>
          <div className="mt-7 grid items-start gap-5 sm:grid-cols-[13rem_minmax(0,1fr)]">
            <label className="grid min-w-0 content-start gap-2">
              <span className="text-[13px] font-medium text-ink">Previous row's stitches</span>
              <input
                inputMode="numeric"
                value={prev}
                onChange={(e) => setPrev(e.target.value.replace(/[^\d]/g, ""))}
                aria-invalid={prevInvalid}
                aria-describedby="prev-help"
                className="num min-h-12 w-full min-w-0 rounded-lg border border-rule-strong bg-card px-3 font-mono text-[18px] text-ink focus:border-accent focus:outline-none"
              />
              <span id="prev-help" className="text-[12px] text-ink-3">
                Leave empty if the row starts its own ring or chain.
              </span>
            </label>
            <label className="grid min-w-0 content-start gap-2">
              <span className="text-[13px] font-medium text-ink">The row</span>
              <input
                value={row}
                onChange={(e) => setRow(e.target.value)}
                className="min-h-12 w-full min-w-0 rounded-lg border border-rule-strong bg-card px-3 font-serif text-[17px] text-ink focus:border-accent focus:outline-none"
              />
              <span className="text-[12px] text-ink-3">For example "Rnd 5: (sc 3, inc) x6 (30)".</span>
            </label>
          </div>
          <button
            type="submit"
            disabled={busy || prevInvalid || !row.trim()}
            className="press mt-7 inline-flex min-h-11 cursor-pointer items-center rounded-lg bg-accent px-5 text-[15px] font-semibold text-accent-ink hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy ? "Checking…" : "Check this row"}
          </button>
        </div>
      </form>
      <section className="sheet px-6 py-8" aria-live="polite" aria-label="Answer">
        <AnimatePresence mode="wait">
          {answer ? (
            <motion.div key={answer.answer} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ type: "spring", stiffness: 220, damping: 24 }}>
              <Verdict size={30} className={tone} weight={status === "ERROR" ? "fill" : "regular"} aria-hidden="true" />
              <p className="mt-4 font-display text-[1.5rem] leading-snug text-ink">{answer.answer}</p>
              {answer.result && <p className="mt-4 font-serif text-[15px] leading-relaxed text-ink-2">{answer.result.explanation}</p>}
            </motion.div>
          ) : (
            <motion.p key="empty" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="font-serif text-[16px] leading-relaxed text-ink-3 italic">
              The answer appears here, with the numbers behind it.
            </motion.p>
          )}
        </AnimatePresence>
      </section>
    </div>
  );
}
