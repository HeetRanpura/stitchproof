import { MagnifyingGlassPlusIcon, XIcon } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";

/** The uploaded photo in a paper frame, overlapping the transcription it produced. Click to zoom. */
export function PhotoFrame({ url, model }: { url: string; model: string }) {
  const [zoom, setZoom] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    if (zoom) dialog.current?.showModal();
    else dialog.current?.close();
  }, [zoom]);

  return (
    <figure className="relative">
      <button
        type="button"
        onClick={() => setZoom(true)}
        className="press group relative block w-full -rotate-[1.5deg] cursor-zoom-in rounded-md border border-rule bg-card p-2.5 pb-9 shadow-[0_18px_36px_-20px_rgb(var(--shadow)/0.45)]"
        aria-label="Zoom the photo"
      >
        <img src={url} alt="Your photo of the pattern page" className="aspect-[4/3] w-full rounded-sm object-cover object-top" />
        <span className="absolute right-3 bottom-2 inline-flex items-center gap-1 font-mono text-[11px] text-ink-3">
          <MagnifyingGlassPlusIcon size={14} aria-hidden="true" /> zoom
        </span>
      </button>
      <figcaption className="mt-4 text-[13px] leading-snug text-ink-2">
        Transcribed by <span className="font-medium text-ink">{model}</span> on this computer. Compare it with the photo and fix anything misread, then check.
      </figcaption>
      <dialog
        ref={dialog}
        onClose={() => setZoom(false)}
        onClick={(e) => e.target === dialog.current && setZoom(false)}
        className="m-auto max-h-[92dvh] max-w-[92vw] rounded-xl border border-rule bg-card p-0 backdrop:bg-black/50"
      >
        <div className="flex items-center justify-between border-b border-rule px-4 py-2">
          <span className="text-sm text-ink-2">Your photo</span>
          <button type="button" onClick={() => setZoom(false)} className="press grid size-10 cursor-pointer place-items-center rounded-full hover:bg-card-2" aria-label="Close">
            <XIcon size={18} />
          </button>
        </div>
        <img src={url} alt="Your photo of the pattern page, full size" className="max-h-[80dvh] w-auto" />
      </dialog>
    </figure>
  );
}
