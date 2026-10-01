"use client";

// Dark (the default), light, or the device's choice. Kept in this browser; applied
// before the first paint by the script in app/layout.tsx.
import { useEffect, useState } from "react";

export type Mode = "system" | "light" | "dark";

function resolve(mode: Mode): "light" | "dark" {
  if (mode !== "system") return mode;
  return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

export function applyTheme(mode: Mode) {
  document.documentElement.dataset.theme = resolve(mode);
  try {
    localStorage.setItem("fct_theme", mode);
  } catch {}
  window.dispatchEvent(new Event("fct-theme"));
}

export function useTheme(): [Mode, "light" | "dark"] {
  const [mode, setMode] = useState<Mode>("dark");
  const [shown, setShown] = useState<"light" | "dark">("dark");
  useEffect(() => {
    const read = () => {
      let saved: string | null = null;
      try {
        saved = localStorage.getItem("fct_theme");
      } catch {}
      setMode(saved === "light" || saved === "system" ? saved : "dark");
      setShown(document.documentElement.dataset.theme === "light" ? "light" : "dark");
    };
    read();
    window.addEventListener("fct-theme", read);
    return () => window.removeEventListener("fct-theme", read);
  }, []);
  return [mode, shown];
}

const icons: Record<"light" | "dark", string> = {
  light: "M12 4V2m0 20v-2m8-8h2M2 12h2m13.66-5.66l1.41-1.41M4.93 19.07l1.41-1.41m0-11.32L4.93 4.93m14.14 14.14l-1.41-1.41M16 12a4 4 0 11-8 0 4 4 0 018 0z",
  dark: "M20 14.5A8 8 0 019.5 4a8 8 0 1010.5 10.5z",
};

/** One button: switches between dark and light. */
export function ThemeButton({ className = "" }: { className?: string }) {
  const [, shown] = useTheme();
  const next = shown === "light" ? "dark" : "light";
  return (
    <button
      type="button"
      onClick={() => applyTheme(next)}
      aria-label={`Switch to ${next} theme`}
      title={`Switch to ${next} theme`}
      className={`inline-flex h-9 w-9 items-center justify-center rounded-lg text-ink2 transition-colors hover:bg-hover hover:text-ink ${className}`}
    >
      <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d={icons[shown]} />
      </svg>
    </button>
  );
}
