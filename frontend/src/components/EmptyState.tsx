import { CameraIcon, ClipboardTextIcon, FilePdfIcon } from "@phosphor-icons/react";
import { StitchChart } from "./StitchMark";

interface Props {
  onPaste: () => void;
  onFile: () => void;
  onPhoto: () => void;
  onExample: () => void;
  photoReady: boolean;
  photoDetail: string;
  demo: boolean;
}

/** First screen: an editorial page, not a form. */
export function EmptyState({ onPaste, onFile, onPhoto, onExample, photoReady, photoDetail, demo }: Props) {
  const actions = [
    { icon: ClipboardTextIcon, title: "Paste the text", body: "Rows, notes and all. One row per line.", onClick: onPaste, disabled: false },
    { icon: FilePdfIcon, title: "Open a file", body: ".txt, .md or a PDF with a text layer.", onClick: onFile, disabled: false },
    {
      icon: CameraIcon,
      title: "Photograph a page",
      body: photoReady ? "Gemma 4 transcribes it on this computer." : `Off: ${photoDetail}.`,
      onClick: onPhoto,
      disabled: !photoReady,
    },
  ];
  return (
    <div className="relative grid gap-10 overflow-hidden px-6 py-10 sm:px-10 md:grid-cols-[1.35fr_1fr] md:py-14">
      <div>
        <p className="font-mono text-[11px] tracking-[0.18em] text-ink-3 uppercase">Before you publish</p>
        <h2
          className="mt-4 font-display text-[2.1rem] leading-[1.08] font-normal tracking-tight text-ink sm:text-[2.6rem]"
          style={{ fontVariationSettings: '"opsz" 120, "SOFT" 80' }}
        >
          Paste a pattern.
          <br />
          <span className="text-ink-2 italic">Every count gets checked.</span>
        </h2>
        <p className="mt-5 max-w-[46ch] font-serif text-[17px] leading-relaxed text-ink-2">
          StitchProof works through your rows in order and flags any round whose instructions don't make the count you wrote, with the numbers to prove it.
        </p>
        {demo && (
          <p className="mt-6 max-w-[52ch] rounded-lg border border-rule bg-card-2 px-4 py-3 text-[14px] leading-relaxed text-ink-2">
            <span className="font-medium text-ink">Demo mode.</span> No model is running: StitchProof replays the fine-tuned model's recorded answers for the sample pattern below. To check your own patterns, start the local model (see the README).
          </p>
        )}
        <ul className="mt-8 grid max-w-md gap-2.5">
          {actions.map((a) => (
            <li key={a.title}>
              <button
                type="button"
                onClick={a.onClick}
                disabled={a.disabled}
                className="press group flex min-h-14 w-full cursor-pointer items-center gap-4 rounded-xl border border-rule bg-card px-4 py-3 text-left hover:border-rule-strong disabled:cursor-not-allowed disabled:opacity-50"
              >
                <a.icon size={22} className="text-accent" aria-hidden="true" />
                <span>
                  <span className="block text-[15px] font-medium text-ink">{a.title}</span>
                  <span className="block text-[13px] text-ink-2">{a.body}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
        <button type="button" onClick={onExample} className="mt-6 cursor-pointer text-[14px] font-medium text-accent underline decoration-1 underline-offset-4 hover:decoration-2">
          Or try a sample pattern with two mistakes in it
        </button>
      </div>
      <div className="relative hidden items-center justify-center md:flex">
        <StitchChart className="w-full max-w-[320px] -rotate-6 opacity-90" />
        <p className="absolute right-0 bottom-2 max-w-[16ch] text-right font-serif text-[13px] leading-snug text-ink-3 italic">
          round 4, stitch 6: the one that doesn't add up
        </p>
      </div>
    </div>
  );
}
