/** The StitchProof mark: a single cross-stitch, drawn like thread. */
export function StitchMark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" className="shrink-0">
      <rect x="1" y="1" width="30" height="30" rx="9" className="fill-accent" />
      <path d="M9.5 9.5c4 4.2 8.6 8.8 13 13" className="stroke-accent-ink" strokeWidth="3" strokeLinecap="round" fill="none" />
      <path d="M22.5 9.5c-4.2 4-8.8 8.6-13 13" className="stroke-accent-ink" strokeWidth="3" strokeLinecap="round" fill="none" opacity="0.9" />
    </svg>
  );
}

/** Hand-drawn round crochet chart (rings of stitch marks), used as the empty-state illustration. */
export function StitchChart({ className = "" }: { className?: string }) {
  const rings = [
    { r: 18, n: 6 },
    { r: 36, n: 12 },
    { r: 54, n: 18 },
    { r: 72, n: 24 },
  ];
  return (
    <svg viewBox="-90 -90 180 180" className={className} aria-hidden="true">
      <circle r="5" className="fill-none stroke-ink-3" strokeWidth="1.2" />
      {rings.map(({ r, n }, ri) => (
        <g key={r}>
          <circle r={r + 8} className="fill-none stroke-rule-strong" strokeWidth="0.7" strokeDasharray="1.5 3" />
          {Array.from({ length: n }, (_, i) => {
            const a = (i / n) * Math.PI * 2 + ri * 0.21;
            const x = Math.cos(a) * r;
            const y = Math.sin(a) * r;
            const deg = (a * 180) / Math.PI;
            const isInc = ri > 0 && i % (ri + 1) === ri;
            const isError = ri === 3 && i === 5;
            return (
              <g key={i} transform={`translate(${x.toFixed(2)} ${y.toFixed(2)}) rotate(${deg.toFixed(1)})`}>
                {isInc ? (
                  <path d="M-3.5 -3 L0 2.5 L3.5 -3" className={isError ? "fill-none stroke-accent" : "fill-none stroke-ink-2"} strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
                ) : (
                  <path d="M-3 -3 L3 3 M3 -3 L-3 3" className={isError ? "stroke-accent" : "stroke-ink-2"} strokeWidth="1.3" strokeLinecap="round" />
                )}
              </g>
            );
          })}
        </g>
      ))}
      <circle cx={Math.cos((5 / 24) * Math.PI * 2 + 0.63) * 72} cy={Math.sin((5 / 24) * Math.PI * 2 + 0.63) * 72} r="8" className="fill-none stroke-accent" strokeWidth="1.2" />
    </svg>
  );
}
