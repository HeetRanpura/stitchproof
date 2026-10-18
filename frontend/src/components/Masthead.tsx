import { CameraIcon, CpuIcon, MoonIcon, SunIcon } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import type { AppStatus } from "../types";
import { StitchMark } from "./StitchMark";

export type Mode = "check" | "row";

function StatusChip({ ok, label, detail, icon }: { ok: boolean | null; label: string; detail: string; icon: React.ReactNode }) {
  const tone = ok === null ? "text-ink-3" : ok ? "text-ok" : "text-warn";
  const dot = ok === null ? "bg-ink-3" : ok ? "bg-ok" : "bg-warn";
  return (
    <span
      className="inline-flex min-h-9 items-center gap-2 rounded-full border border-rule bg-card px-3 py-1.5 text-[13px] text-ink-2"
      title={detail}
    >
      <span className={`size-1.5 rounded-full ${dot} ${ok ? "breathe" : ""}`} aria-hidden="true" />
      <span className={tone} aria-hidden="true">
        {icon}
      </span>
      <span>
        {label}
        <span className="sr-only">: {detail}</span>
      </span>
    </span>
  );
}

function ModeSwitch({ mode, onChange }: { mode: Mode; onChange: (m: Mode) => void }) {
  const opts: { id: Mode; label: string }[] = [
    { id: "check", label: "Check a pattern" },
    { id: "row", label: "Stuck on a row" },
  ];
  return (
    <div role="group" aria-label="Mode" className="inline-flex rounded-full border border-rule bg-card p-1">
      {opts.map((o) => (
        <button
          key={o.id}
          type="button"
          aria-pressed={mode === o.id}
          onClick={() => onChange(o.id)}
          className={`press min-h-10 cursor-pointer rounded-full px-4 text-sm font-medium whitespace-nowrap ${
            mode === o.id ? "bg-ink text-paper" : "text-ink-2 hover:text-ink"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

type Theme = "light" | "dark";

function systemTheme(): Theme {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function storedTheme(): Theme | null {
  try {
    const t = localStorage.getItem("stitchproof-theme");
    return t === "light" || t === "dark" ? t : null;
  } catch {
    return null;
  }
}

/** Light/dark switch. Follows the system until the user picks one; the choice is remembered on this browser. */
function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(() => storedTheme() ?? systemTheme());

  useEffect(() => {
    const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
    const follow = () => storedTheme() === null && setTheme(systemTheme());
    mq?.addEventListener("change", follow);
    return () => mq?.removeEventListener("change", follow);
  }, []);

  function toggle() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("stitchproof-theme", next);
    } catch {
      /* private mode: the switch still works for this visit */
    }
  }

  const Icon = theme === "dark" ? SunIcon : MoonIcon;
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
      title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
      className="press inline-flex min-h-10 cursor-pointer items-center gap-2 rounded-full border border-rule bg-card px-3.5 text-sm font-medium text-ink-2 hover:text-ink"
    >
      <Icon size={17} aria-hidden="true" />
      <span>{theme === "dark" ? "Light" : "Dark"}</span>
    </button>
  );
}

export function Masthead({ status, mode, onMode }: { status: AppStatus | null; mode: Mode; onMode: (m: Mode) => void }) {
  const model = status?.model;
  const photo = status?.photo_reader;
  return (
    <header className="flex flex-col gap-6 pt-8 md:pt-12 lg:flex-row lg:items-end lg:justify-between">
      <div className="max-w-xl">
        <div className="flex items-center gap-3">
          <StitchMark />
          <h1 className="font-display text-[2rem] leading-none font-medium tracking-tight text-ink md:text-[2.4rem]" style={{ fontVariationSettings: '"opsz" 96, "SOFT" 50' }}>
            StitchProof
          </h1>
        </div>
        <p className="mt-3 text-[15px] leading-relaxed text-ink-2">
          A tech editor for crochet patterns. A small local model reads each row; plain code checks every stitch count.
        </p>
      </div>
      <div className="flex flex-col gap-3 lg:items-end">
        <div className="flex flex-wrap gap-2">
          <StatusChip
            ok={model ? model.ready : null}
            icon={<CpuIcon size={15} />}
            label={model ? (model.ready ? "Model ready · on this computer" : "Model offline") : "Checking model…"}
            detail={model ? `${model.name}: ${model.detail}` : "contacting the local server"}
          />
          <StatusChip
            ok={photo ? photo.ready : null}
            icon={<CameraIcon size={15} />}
            label={photo ? (photo.ready ? "Photo reader · Gemma 4" : "Photo reader off") : "Photo reader…"}
            detail={photo ? photo.detail : "checking Ollama"}
          />
        </div>
        <div className="flex flex-wrap items-center gap-2 lg:justify-end">
          <ThemeToggle />
          <ModeSwitch mode={mode} onChange={onMode} />
        </div>
      </div>
    </header>
  );
}
