"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";

export function Seal({ size = 40, className = "" }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 96 96" aria-hidden="true" className={`shrink-0 ${className}`}>
      <rect width="96" height="96" rx="26" fill="#0E6B4F" />
      <circle cx="48" cy="48" r="31" fill="none" stroke="#fff" strokeWidth="3.2" strokeDasharray="3.8 3.2" />
      <circle cx="48" cy="48" r="23.5" fill="#fff" />
      <text x="48" y="61" textAnchor="middle" fontFamily="var(--font-newsreader), Georgia, serif" fontSize="36" fontWeight="600" fill="#0E6B4F">
        F
      </text>
      <circle cx="67" cy="67" r="12.4" fill="#0E6B4F" />
      <circle cx="67" cy="67" r="10" fill="#7FE0B8" />
      <path d="M62.4 67.2l3.2 3.2 6.2-6.8" fill="none" stroke="#0E6B4F" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function Wordmark({ size = 32 }: { size?: number }) {
  return (
    <Link href="/" className="flex items-center gap-2.5 font-serif text-2xl font-semibold tracking-tight text-ink">
      <Seal size={size} />
      <span>Factify</span>
    </Link>
  );
}

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "outline" | "ghost" | "danger";
  busy?: boolean;
  size?: "sm" | "md" | "lg";
};

export function Button({ variant = "primary", busy, size = "md", className = "", children, disabled, ...rest }: ButtonProps) {
  const base =
    "inline-flex items-center justify-center gap-2 rounded-xl font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50 whitespace-nowrap";
  const sizes = { sm: "h-9 px-3 text-sm", md: "h-11 px-4 text-[15px]", lg: "h-12 px-6 text-base" };
  const variants = {
    primary: "bg-acc text-on-acc hover:brightness-110",
    outline: "border border-line bg-sf text-ink hover:bg-sf2",
    ghost: "text-ink2 hover:bg-sf2 hover:text-ink",
    danger: "border border-line bg-sf text-false hover:bg-false-soft",
  };
  return (
    <button
      className={`${base} ${sizes[size]} ${variants[variant]} ${className}`}
      disabled={disabled || busy}
      {...rest}
    >
      {busy && <Spinner />}
      {children}
    </button>
  );
}

export function Spinner({ className = "" }: { className?: string }) {
  return (
    <span
      className={`inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent ${className}`}
      aria-hidden="true"
    />
  );
}

export function Card({ className = "", children }: { className?: string; children: React.ReactNode }) {
  return <div className={`min-w-0 rounded-2xl border border-line bg-sf p-4 shadow-card sm:p-5 ${className}`}>{children}</div>;
}

export function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string;
  hint?: string;
  error?: string | null;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-semibold text-ink2">{label}</span>
      {children}
      {hint && !error && <span className="mt-1 block text-xs text-ink3">{hint}</span>}
      {error && <span className="mt-1 block text-xs text-false">{error}</span>}
    </label>
  );
}

export const inputClass =
  "w-full rounded-xl border border-line bg-sf px-3.5 py-2.5 text-[15px] text-ink placeholder:text-ink3 focus:border-acc focus:outline-none";

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`${inputClass} ${props.className ?? ""}`} />;
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={`${inputClass} ${props.className ?? ""}`} />;
}

export function Notice({ tone = "info", children }: { tone?: "info" | "error" | "warning" | "success"; children: React.ReactNode }) {
  const tones = {
    info: "bg-sf2 text-ink2",
    error: "bg-false-soft text-false",
    warning: "bg-mis-soft text-mis",
    success: "bg-acc-soft text-acc-ink",
  };
  return (
    <div role={tone === "error" ? "alert" : "status"} className={`rounded-xl px-3.5 py-2.5 text-sm ${tones[tone]}`}>
      {children}
    </div>
  );
}

export function Badge({ tone = "neutral", children }: { tone?: "neutral" | "acc" | "warn" | "bad"; children: React.ReactNode }) {
  const tones = {
    neutral: "bg-sf2 text-ink2",
    acc: "bg-acc-soft text-acc-ink",
    warn: "bg-mis-soft text-mis",
    bad: "bg-false-soft text-false",
  };
  return <span className={`inline-flex items-center rounded-lg px-2 py-0.5 text-xs font-semibold ${tones[tone]}`}>{children}</span>;
}

export function Stat({
  label,
  value,
  sub,
  icon,
  trend,
  tone = "neutral",
}: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  icon?: React.ReactNode;
  trend?: React.ReactNode;
  tone?: "neutral" | "acc" | "warn" | "bad";
}) {
  const tones = {
    neutral: "bg-sf2 text-ink2",
    acc: "bg-acc-soft text-acc-ink",
    warn: "bg-mis-soft text-mis",
    bad: "bg-false-soft text-false",
  };
  return (
    <div className="fade-in min-w-0 rounded-2xl border border-line bg-sf p-4 shadow-card">
      <div className="flex items-center justify-between gap-2">
        <div className="truncate text-[13px] font-medium text-ink3">{label}</div>
        {icon && <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-xl ${tones[tone]}`}>{icon}</div>}
      </div>
      <div className="tabular mt-2 font-serif text-[2rem] leading-none font-medium tracking-tight text-ink">{value}</div>
      {sub && <div className="mt-1.5 truncate text-xs text-ink3">{sub}</div>}
      {trend && <div className="mt-2 text-acc-ink">{trend}</div>}
    </div>
  );
}

const avatarTones = ["bg-[#dcefe6] text-[#0e6b4f]", "bg-[#efe4cf] text-[#7a5a1c]", "bg-[#e6e1f6] text-[#4b3f8f]", "bg-[#fbe3dc] text-[#9a3a1f]", "bg-[#dfeaf5] text-[#1f4f7a]"];

export function Avatar({ name, size = 36 }: { name: string; size?: number }) {
  const letters = name
    .replace(/@.*/, "")
    .split(/[\s._-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase())
    .join("");
  const tone = avatarTones[[...name].reduce((h, c) => h + c.charCodeAt(0), 0) % avatarTones.length];
  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center rounded-full font-semibold ${tone}`}
      style={{ width: size, height: size, fontSize: size * 0.38 }}
      aria-hidden="true"
    >
      {letters || "?"}
    </span>
  );
}

/** Used of a limit, as a thin bar; turns amber then red as it fills. */
export function Progress({ used, total }: { used: number; total: number | null | undefined }) {
  if (!total) return <div className="h-1.5 rounded-full bg-sf2" />;
  const f = Math.min(1, used / total);
  const tone = f >= 0.9 ? "bg-false" : f >= 0.7 ? "bg-mis" : "bg-acc";
  return (
    <div className="h-1.5 overflow-hidden rounded-full bg-sf2" role="progressbar" aria-valuenow={used} aria-valuemax={total}>
      <div className={`h-full rounded-full ${tone}`} style={{ width: `${Math.max(2, f * 100)}%` }} />
    </div>
  );
}

/** Section tabs as links, scrolling sideways on a narrow screen. */
export function TabLinks({ tabs, active }: { tabs: { href: string; label: string; count?: number }[]; active: string }) {
  return (
    <div className="-mx-4 mb-6 overflow-x-auto px-4 sm:mx-0 sm:px-0">
      <div className="flex w-max gap-1 border-b border-line">
        {tabs.map((t) => (
          <Link
            key={t.href}
            href={t.href}
            aria-current={active === t.href ? "page" : undefined}
            className={`-mb-px flex items-center gap-2 border-b-2 px-3.5 py-2.5 text-sm font-semibold whitespace-nowrap ${
              active === t.href ? "border-acc text-ink" : "border-transparent text-ink3 hover:text-ink"
            }`}
          >
            {t.label}
            {t.count != null && <span className="tabular rounded-md bg-sf2 px-1.5 py-0.5 text-[11px] text-ink2">{t.count}</span>}
          </Link>
        ))}
      </div>
    </div>
  );
}

export function PageTitle({
  title,
  sub,
  action,
  eyebrow,
}: {
  title: React.ReactNode;
  sub?: React.ReactNode;
  action?: React.ReactNode;
  eyebrow?: React.ReactNode;
}) {
  return (
    <div className="mb-7 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        {eyebrow && <div className="mb-1.5 text-xs font-semibold tracking-[0.12em] text-acc-ink uppercase">{eyebrow}</div>}
        <h1 className="font-serif text-[2rem] leading-[1.05] font-medium tracking-tight text-ink sm:text-[2.6rem]">{title}</h1>
        {sub && <p className="mt-2 max-w-2xl text-[15px] text-ink2">{sub}</p>}
      </div>
      {action && <div className="flex shrink-0 flex-wrap gap-2">{action}</div>}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-dashed border-line px-5 py-10 text-center">
      <div className="font-serif text-xl text-ink">{title}</div>
      {children && <div className="mx-auto mt-2 max-w-md text-sm text-ink2">{children}</div>}
    </div>
  );
}

/** A table that scrolls sideways inside itself on a narrow screen, never the page. */
export function Table({ head, children }: { head: React.ReactNode[]; children: React.ReactNode }) {
  return (
    <div className="-mx-4 overflow-x-auto sm:mx-0">
      <table className="w-full min-w-[640px] border-separate border-spacing-0 text-sm">
        <thead>
          <tr>
            {head.map((h, i) => (
              <th key={i} className="border-b border-line px-4 py-2.5 text-left font-semibold whitespace-nowrap text-ink3">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="[&_td]:border-b [&_td]:border-line [&_td]:px-4 [&_td]:py-3 [&_td]:align-middle">{children}</tbody>
      </table>
    </div>
  );
}

export function Modal({
  open,
  title,
  onClose,
  children,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);
  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onClick={(e) => e.target === ref.current && onClose()}
      className="m-auto w-[calc(100%-2rem)] max-w-lg rounded-2xl border border-line bg-sf p-0 text-ink backdrop:bg-black/40"
    >
      <div className="max-h-[85vh] overflow-y-auto p-5 sm:p-6">
        <div className="mb-4 flex items-start justify-between gap-4">
          <h2 className="font-serif text-2xl text-ink">{title}</h2>
          <button onClick={onClose} aria-label="Close" className="-mr-2 -mt-1 rounded-lg p-2 text-ink3 hover:bg-sf2">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </div>
        {children}
      </div>
    </dialog>
  );
}

/** Credits by day, as bars. The number each bar stands for is in its label. */
export function Bars({ data }: { data: { label: string; value: number }[] }) {
  if (!data.length) return <div className="py-8 text-center text-sm text-ink3">No checks in this period yet.</div>;
  const max = Math.max(...data.map((d) => d.value), 1);
  return (
    <div>
      <div className="flex h-40 items-end gap-[3px]" role="img" aria-label="Credits used per day">
        {data.map((d) => (
          <div key={d.label} className="group relative flex h-full min-w-0 flex-1 items-end">
            <div
              className="w-full rounded-t-[4px] bg-acc/80 transition-colors group-hover:bg-acc"
              style={{ height: `${Math.max(3, (d.value / max) * 100)}%` }}
              title={`${d.label}: ${d.value} credits`}
            />
          </div>
        ))}
      </div>
      <div className="mt-2 flex justify-between text-xs text-ink3">
        <span>{data[0].label}</span>
        <span>{data[data.length - 1].label}</span>
      </div>
    </div>
  );
}

export function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  return (
    <Button
      variant="outline"
      size="sm"
      onClick={async (e) => {
        const button = e.currentTarget;
        await navigator.clipboard.writeText(text).catch(() => undefined);
        const old = button.textContent;
        button.textContent = "Copied";
        setTimeout(() => (button.textContent = old), 1500);
      }}
    >
      {label}
    </Button>
  );
}
