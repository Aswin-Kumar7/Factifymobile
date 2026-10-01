"use client";

// Small, dependency-free charts in the dashboard's colours. Every chart has a text
// equivalent (its label, or the numbers beside it), so colour is never the only cue.

import { useId, useMemo, useRef, useState } from "react";
import { n } from "@/lib/format";

export type Point = { label: string; value: number; extra?: number };

/** Days as an area chart with gridlines and a hover read-out. */
export function AreaChart({
  data,
  height = 220,
  unit = "credits",
  extraLabel,
}: {
  data: Point[];
  height?: number;
  unit?: string;
  extraLabel?: string;
}) {
  const id = useId().replace(/:/g, "");
  const box = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<number | null>(null);
  const width = 720;
  const pad = { l: 36, r: 12, t: 14, b: 24 };
  const max = useMemo(() => {
    const top = Math.max(1, ...data.map((d) => Math.max(d.value, d.extra ?? 0)));
    const step = Math.pow(10, Math.floor(Math.log10(top)));
    return Math.ceil(top / step) * step;
  }, [data]);
  if (!data.length) return <div className="py-12 text-center text-sm text-ink3">Nothing in this period yet.</div>;

  const x = (i: number) => pad.l + (i * (width - pad.l - pad.r)) / Math.max(1, data.length - 1);
  const y = (v: number) => pad.t + (1 - v / max) * (height - pad.t - pad.b);
  const line = (key: "value" | "extra") =>
    data.map((d, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y((key === "value" ? d.value : d.extra) ?? 0).toFixed(1)}`).join("");
  const area = `${line("value")}L${x(data.length - 1)},${y(0)}L${x(0)},${y(0)}Z`;
  const ticks = [...new Set([0, 0.5, 1].map((f) => Math.round(max * f)))];
  const hasExtra = data.some((d) => d.extra !== undefined);

  function move(e: React.PointerEvent) {
    const rect = box.current?.getBoundingClientRect();
    if (!rect) return;
    const rel = ((e.clientX - rect.left) / rect.width) * width;
    const i = Math.round(((rel - pad.l) / (width - pad.l - pad.r)) * (data.length - 1));
    setHover(Math.min(data.length - 1, Math.max(0, i)));
  }

  const h = hover != null ? data[hover] : null;
  return (
    <div ref={box} className="relative select-none" onPointerMove={move} onPointerLeave={() => setHover(null)}>
      <svg viewBox={`0 0 ${width} ${height}`} className="h-auto w-full" role="img" aria-label={`${unit} per day`}>
        <defs>
          <linearGradient id={`g${id}`} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="var(--chart-1)" stopOpacity="0.32" />
            <stop offset="100%" stopColor="var(--chart-1)" stopOpacity="0" />
          </linearGradient>
        </defs>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={pad.l} x2={width - pad.r} y1={y(t)} y2={y(t)} stroke="var(--grid)" strokeDasharray={t ? "3 4" : undefined} />
            <text x={pad.l - 8} y={y(t) + 4} textAnchor="end" className="fill-ink3 text-[11px]">
              {n(t)}
            </text>
          </g>
        ))}
        <path d={area} fill={`url(#g${id})`} />
        <path d={line("value")} fill="none" stroke="var(--chart-1)" strokeWidth="2.2" strokeLinejoin="round" strokeLinecap="round" />
        {hasExtra && (
          <path d={line("extra")} fill="none" stroke="var(--chart-3)" strokeWidth="1.8" strokeDasharray="5 5" strokeLinejoin="round" />
        )}
        {[0, Math.floor((data.length - 1) / 2), data.length - 1].map((i) => (
          <text key={i} x={x(i)} y={height - 6} textAnchor={i === 0 ? "start" : i === data.length - 1 ? "end" : "middle"} className="fill-ink3 text-[11px]">
            {data[i].label}
          </text>
        ))}
        {hover != null && (
          <g>
            <line x1={x(hover)} x2={x(hover)} y1={pad.t} y2={y(0)} stroke="var(--ink3)" strokeOpacity="0.4" />
            <circle cx={x(hover)} cy={y(data[hover].value)} r="4.5" fill="var(--sf)" stroke="var(--chart-1)" strokeWidth="2.2" />
          </g>
        )}
      </svg>
      {h && hover != null && (
        <div
          className="pointer-events-none absolute top-0 rounded-xl border border-line bg-sf px-3 py-2 text-xs shadow-lift"
          style={{ left: `${Math.min(80, Math.max(2, (x(hover) / width) * 100 - 8))}%` }}
        >
          <div className="font-semibold text-ink">{h.label}</div>
          <div className="tabular text-ink2">
            {n(h.value)} {unit}
          </div>
          {h.extra !== undefined && (
            <div className="tabular text-ink3">
              {n(h.extra)} {extraLabel}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** A tiny trend line for a stat. */
export function Sparkline({ values, className = "" }: { values: number[]; className?: string }) {
  if (values.length < 2) return null;
  const max = Math.max(1, ...values);
  const w = 100;
  const h = 28;
  const pts = values.map((v, i) => `${(i * w) / (values.length - 1)},${h - 2 - (v / max) * (h - 4)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className={`h-7 w-full ${className}`} aria-hidden="true">
      <polyline points={pts} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

/** How much of something is used, as a ring with the number in the middle. */
export function Ring({
  used,
  total,
  size = 132,
  label,
  sub,
}: {
  used: number;
  total: number;
  size?: number;
  label: React.ReactNode;
  sub?: React.ReactNode;
}) {
  const r = 44;
  const c = 2 * Math.PI * r;
  const f = total > 0 ? Math.min(1, used / total) : 0;
  const tone = f >= 0.9 ? "var(--false)" : f >= 0.7 ? "var(--mis)" : "var(--chart-1)";
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg viewBox="0 0 100 100" className="h-full w-full -rotate-90" aria-hidden="true">
        <circle cx="50" cy="50" r={r} fill="none" stroke="var(--sf2)" strokeWidth="9" />
        <circle
          cx="50"
          cy="50"
          r={r}
          fill="none"
          stroke={tone}
          strokeWidth="9"
          strokeLinecap="round"
          strokeDasharray={`${f * c} ${c}`}
          style={{ transition: "stroke-dasharray .6s ease" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
        <div className="tabular text-2xl font-medium tracking-tight text-ink">{label}</div>
        {sub && <div className="text-[11px] text-ink3">{sub}</div>}
      </div>
    </div>
  );
}

/** Shares of a whole, as a horizontal stacked bar with a legend. */
export function Split({ parts }: { parts: { label: string; value: number }[] }) {
  const total = parts.reduce((s, p) => s + p.value, 0);
  const colours = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)", "var(--ink3)"];
  if (!total) return <div className="text-sm text-ink3">No data yet.</div>;
  return (
    <div>
      <div className="flex h-2.5 overflow-hidden rounded-full bg-sf2">
        {parts.map((p, i) => (
          <div key={p.label} style={{ width: `${(p.value / total) * 100}%`, background: colours[i % colours.length] }} />
        ))}
      </div>
      <ul className="mt-3 space-y-1.5 text-sm">
        {parts.map((p, i) => (
          <li key={p.label} className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: colours[i % colours.length] }} />
            <span className="min-w-0 flex-1 truncate text-ink2">{p.label}</span>
            <span className="tabular text-ink">{n(p.value)}</span>
            <span className="tabular w-10 text-right text-xs text-ink3">{Math.round((p.value / total) * 100)}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Fill the gaps: one point per day for the last `days` days. */
export function daily(rows: { day: string; credits?: number; checks?: number }[], days: number, key: "credits" | "checks" = "credits"): Point[] {
  const map = new Map(rows.map((r) => [r.day, Number(r[key] ?? 0)]));
  return Array.from({ length: days }, (_, i) => {
    const d = new Date(Date.now() - (days - 1 - i) * 86400000).toISOString().slice(0, 10);
    const date = new Date(d);
    return { label: date.toLocaleDateString("en-IN", { day: "numeric", month: "short" }), value: map.get(d) ?? 0 };
  });
}
