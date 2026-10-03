"use client";

import { useState } from "react";

/** Copy a value, saying so for a moment. */
export function CopyButton({ value, label = "Copy" }: { value: string; label?: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      onClick={() => {
        void navigator.clipboard?.writeText(value).then(() => {
          setDone(true);
          setTimeout(() => setDone(false), 1400);
        });
      }}
      className="inline-flex h-7 items-center gap-1.5 rounded-md border border-white/10 px-2 text-[12px] text-[#a9b6ae] transition-colors hover:bg-white/10 hover:text-white"
      aria-label={`${label} to clipboard`}
    >
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        {done ? <path d="M5 12.5l4.5 4.5L19 7.5" /> : <path d="M9 9h10v10H9zM5 15V5h10" />}
      </svg>
      {done ? "Copied" : label}
    </button>
  );
}

export type Sample = { lang: string; code: string };

/** A code sample in several languages, one shown at a time, with a copy button. */
export function CodeTabs({ title, samples }: { title?: string; samples: Sample[] }) {
  const [at, setAt] = useState(0);
  const shown = samples[Math.min(at, samples.length - 1)];
  return (
    <div className="overflow-hidden rounded-2xl border border-white/10 bg-[#0b100d] shadow-lg">
      <div className="flex items-center justify-between gap-3 border-b border-white/10 px-3 py-2">
        <div className="flex min-w-0 items-center gap-1" role="tablist" aria-label={title || "Code sample"}>
          {title && <span className="mr-2 hidden truncate font-mono text-[11.5px] text-[#76847c] sm:inline">{title}</span>}
          {samples.map((s, i) => (
            <button
              key={s.lang}
              type="button"
              role="tab"
              aria-selected={i === at}
              onClick={() => setAt(i)}
              className={`rounded-md px-2.5 py-1 text-[12px] transition-colors ${
                i === at ? "bg-white/10 text-white" : "text-[#8a978f] hover:text-white"
              }`}
            >
              {s.lang}
            </button>
          ))}
        </div>
        <CopyButton value={shown.code} />
      </div>
      <pre className="max-h-[440px] overflow-auto p-4 font-mono text-[12.5px] leading-[1.75] text-[#dfe9e3]">
        <code>{shown.code}</code>
      </pre>
    </div>
  );
}
