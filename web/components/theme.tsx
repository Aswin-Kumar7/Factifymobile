"use client";

// Dark (the default) or light, switched by the button in the top bar. Kept in this
// browser; applied before the first paint by the script in app/layout.tsx.
import { useEffect, useState } from "react";

type Shown = "light" | "dark";

function applyTheme(mode: Shown) {
  document.documentElement.dataset.theme = mode;
  try {
    localStorage.setItem("fct_theme", mode);
  } catch {}
  window.dispatchEvent(new Event("fct-theme"));
}

function useTheme(): Shown {
  const [shown, setShown] = useState<Shown>("dark");
  useEffect(() => {
    const read = () => setShown(document.documentElement.dataset.theme === "light" ? "light" : "dark");
    read();
    window.addEventListener("fct-theme", read);
    return () => window.removeEventListener("fct-theme", read);
  }, []);
  return shown;
}

const icons: Record<Shown, string> = {
  light: "M12 4V2m0 20v-2m8-8h2M2 12h2m13.66-5.66l1.41-1.41M4.93 19.07l1.41-1.41m0-11.32L4.93 4.93m14.14 14.14l-1.41-1.41M16 12a4 4 0 11-8 0 4 4 0 018 0z",
  dark: "M20 14.5A8 8 0 019.5 4a8 8 0 1010.5 10.5z",
};

/** One button: switches between dark and light. */
export function ThemeButton({ className = "" }: { className?: string }) {
  const shown = useTheme();
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
