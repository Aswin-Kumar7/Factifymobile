"use client";

// Light, dark, or the system's choice. Kept in this browser; applied before the
// first paint by the script in app/layout.tsx.
import { useEffect, useState } from "react";

type Mode = "system" | "light" | "dark";

function apply(mode: Mode) {
  const root = document.documentElement;
  if (mode === "system") delete root.dataset.theme;
  else root.dataset.theme = mode;
  try {
    if (mode === "system") localStorage.removeItem("fct_theme");
    else localStorage.setItem("fct_theme", mode);
  } catch {}
}

const icons: Record<Mode, string> = {
  light: "M12 4V2m0 20v-2m8-8h2M2 12h2m13.66-5.66l1.41-1.41M4.93 19.07l1.41-1.41m0-11.32L4.93 4.93m14.14 14.14l-1.41-1.41M16 12a4 4 0 11-8 0 4 4 0 018 0z",
  system: "M4 5h16v11H4zM9 20h6M12 16v4",
  dark: "M21 12.8A9 9 0 1111.2 3a7 7 0 009.8 9.8z",
};

export function ThemeToggle({ onDark = false }: { onDark?: boolean }) {
  const [mode, setMode] = useState<Mode>("system");
  useEffect(() => {
    try {
      const saved = localStorage.getItem("fct_theme");
      if (saved === "light" || saved === "dark") setMode(saved);
    } catch {}
  }, []);
  return (
    <div
      role="radiogroup"
      aria-label="Theme"
      className={`inline-flex rounded-xl p-1 ${onDark ? "bg-side-2" : "bg-sf2"}`}
    >
      {(["light", "system", "dark"] as Mode[]).map((m) => (
        <button
          key={m}
          role="radio"
          aria-checked={mode === m}
          aria-label={m === "system" ? "Same as device" : m === "light" ? "Light" : "Dark"}
          title={m === "system" ? "Same as device" : m === "light" ? "Light" : "Dark"}
          onClick={() => {
            setMode(m);
            apply(m);
          }}
          className={`flex h-8 w-9 items-center justify-center rounded-lg transition-colors ${
            mode === m
              ? onDark
                ? "bg-side text-side-ink shadow-sm"
                : "bg-sf text-ink shadow-sm"
              : onDark
                ? "text-side-ink2 hover:text-side-ink"
                : "text-ink3 hover:text-ink"
          }`}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d={icons[m]} />
          </svg>
        </button>
      ))}
    </div>
  );
}
