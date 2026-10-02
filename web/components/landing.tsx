"use client";

// The landing page's moving and clickable parts: the product shot you can click
// around (an illustration with made-up data, and labelled so), the laptop that shows a check happening (the only animation on the page),
// the feature tabs and the price toggles.

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { API_CHECK_INR, EXTRA_CHECK_INR, PERSONAL, perMonth, Plan, rupees, TEAM } from "@/lib/plans";

const arrow = (
  <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className="transition-transform group-hover:translate-x-0.5" aria-hidden="true">
    <path d="M3 8h10M9 4l4 4-4 4" />
  </svg>
);

const tick = (cls = "text-acc-ink") => (
  <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className={`mt-0.5 shrink-0 ${cls}`} aria-hidden="true">
    <path d="M3.5 8.5l3 3 6-7" />
  </svg>
);

function Tag({ tone, children }: { tone: "false" | "true" | "mis" | "unc"; children: React.ReactNode }) {
  const t = { false: "bg-false-soft text-false", true: "bg-true-soft text-true", mis: "bg-mis-soft text-mis", unc: "bg-unc-soft text-unc" }[tone];
  return <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium whitespace-nowrap ${t}`}>{children}</span>;
}

// ---- the product shot ----------------------------------------------------------------

type View = "check" | "new" | "history" | "usage";

export function ProductShot() {
  const [view, setView] = useState<View>("check");
  const nav: [View, string, string][] = [
    ["check", "Check", "M8.5 12.2l2.4 2.4 4.6-4.9M20.5 12a8.5 8.5 0 11-17 0 8.5 8.5 0 0117 0z"],
    ["history", "History", "M12 8v4.5l3 1.8M4 12a8 8 0 102.3-5.6M4 4.5v3.6h3.6"],
    ["usage", "Plan & usage", "M3.5 6h17v12h-17zM3.5 10h17"],
  ];
  const path = { check: "check", new: "check", history: "history", usage: "plan" }[view];
  return (
    <div className="relative overflow-hidden rounded-[22px] border border-line px-4 pt-10 sm:px-16 sm:pt-16" style={{ background: "radial-gradient(ellipse 70% 80% at 20% 0%, var(--glow), transparent 60%), radial-gradient(ellipse 60% 70% at 100% 100%, var(--glow-2), transparent 70%), var(--wall)" }}>
      <svg viewBox="0 0 1200 700" preserveAspectRatio="none" className="pointer-events-none absolute inset-0 h-full w-full" style={{ color: "var(--contour)" }} aria-hidden="true">
        <g fill="none" stroke="currentColor" strokeWidth="1">
          {[120, 170, 220, 270, 320, 370, 420, 470].map((y) => (
            <path key={y} d={`M-40 ${y} C 220 ${y - 80}, 420 ${y + 100}, 700 ${y + 20} S 1100 ${y - 80}, 1260 ${y}`} />
          ))}
        </g>
      </svg>
      <div className="relative overflow-hidden rounded-t-xl border border-b-0 border-line2 bg-bg shadow-[0_-20px_80px_-30px_rgba(0,0,0,.5)]">
        <div className="flex h-9.5 items-center gap-1.5 border-b border-line bg-sf px-3.5">
          <span className="h-2.5 w-2.5 rounded-full bg-line2" />
          <span className="h-2.5 w-2.5 rounded-full bg-line2" />
          <span className="h-2.5 w-2.5 rounded-full bg-line2" />
          <span className="mx-auto font-mono text-xs text-ink3">Factify · {path}</span>
          <span className="rounded-md bg-hover px-2 py-0.5 text-[11px] text-ink2">Example</span>
        </div>
        <div className="grid h-[540px] grid-cols-1 sm:grid-cols-[210px_minmax(0,1fr)]">
          <div className="hidden flex-col gap-0.5 border-r border-side-line bg-side px-2.5 py-3.5 sm:flex">
            <div className="flex items-center gap-2 px-2 pb-3 text-sm font-semibold text-side-ink">
              <svg width="18" height="18" viewBox="0 0 32 32" fill="none" className="text-acc-ink" aria-hidden="true">
                <circle cx="16" cy="16" r="14.5" stroke="currentColor" strokeWidth="1.8" />
                <path d="M10.8 16.6l3.5 3.5 7.2-7.6" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              Factify
            </div>
            <button type="button" onClick={() => setView("new")} className="mb-2 h-8.5 rounded-lg bg-acc text-[13px] font-medium text-on-acc hover:bg-acc-h">
              + New check
            </button>
            {nav.map(([id, label, d]) => {
              const on = view === id || (id === "check" && view === "new");
              return (
                <button
                  key={id}
                  type="button"
                  onClick={() => setView(id)}
                  className={`flex h-8 items-center gap-2.5 rounded-[7px] px-2.5 text-left text-[13px] transition-colors ${on ? "bg-acc-soft text-side-ink" : "text-side-ink2 hover:bg-side-2 hover:text-side-ink"}`}
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className={on ? "text-acc-ink" : ""} aria-hidden="true">
                    <path d={d} />
                  </svg>
                  {label}
                </button>
              );
            })}
            <div className="mt-auto flex flex-col gap-2">
              <div className="rounded-[9px] border border-hero-line bg-hero px-2.5 py-2.5 text-hero-ink">
                <div className="flex justify-between text-xs text-hero-ink2">
                  <span>This month</span>
                  <span className="text-hero-ink">78 / 120</span>
                </div>
                <div className="mt-2 h-[3px] rounded bg-hero-line">
                  <div className="h-full w-[65%] rounded bg-hero-acc" />
                </div>
              </div>
              <div className="flex items-center gap-2 p-1">
                <span className="flex h-6.5 w-6.5 items-center justify-center rounded-full bg-gradient-to-br from-[#2fb980] to-[#0d3b2a] text-[10px] font-semibold text-white">AR</span>
                <span>
                  <span className="block text-[12.5px] text-side-ink">Asha Rao</span>
                  <span className="block text-[11px] text-acc-ink">Plus plan</span>
                </span>
              </div>
            </div>
          </div>

          <div className="relative overflow-hidden">
            {view === "check" && (
              <div key="check" className="fade-in grid content-start gap-5 p-5 sm:p-7 lg:grid-cols-[minmax(0,1fr)_250px]">
                <div className="flex min-w-0 flex-col gap-3.5">
                  <div className="flex items-center gap-2.5 rounded-[10px] border border-line px-3 py-2.5 text-[13px] text-ink2">
                    <Tag tone="unc">Picture</Tag>
                    <span className="truncate">Massive lithium reserves discovered in Antarctica — energy prices to fall 70%!</span>
                  </div>
                  <div className="overflow-hidden rounded-xl border border-line2">
                    <div className="bg-linear-to-b from-false-soft to-sf px-5 py-4.5">
                      <div className="font-mono text-[10.5px] tracking-[0.14em] text-false">VERDICT</div>
                      <div className="mt-0.5 flex items-baseline gap-3">
                        <span className="text-[2.25rem] font-medium tracking-tight text-false">False</span>
                        <Tag tone="false">70% confidence</Tag>
                      </div>
                      <p className="mt-1.5 text-[13.5px] leading-relaxed text-ink2">No trusted newsroom reports this find, and the picture shows strong signs of being AI-made.</p>
                    </div>
                    <div className="flex flex-col gap-2.5 border-t border-line px-5 py-3.5 text-[13px]">
                      {(
                        [
                          ["Lithium found in Antarctica", "Not reported", "text-false"],
                          ["Energy prices to fall 70%", "No source", "text-false"],
                          ["The picture", "Likely AI-made", "text-mis"],
                        ] as const
                      ).map(([a, b, t]) => (
                        <div key={a} className="flex justify-between gap-3">
                          <span className="text-ink2">{a}</span>
                          <span className={t}>{b}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
                <div className="hidden flex-col gap-2 lg:flex">
                  <span className="eyebrow text-[10.5px]">Evidence · 17 pages read</span>
                  {(
                    [
                      ["Wire service", "No report of the find", "text-ink3"],
                      ["National daily, science desk", "No report of the find", "text-ink3"],
                      ["Picture check", "AI-made signal · strong", "text-mis"],
                    ] as const
                  ).map(([a, b, t]) => (
                    <div key={a} className="flex flex-col gap-0.5 rounded-[10px] border border-line px-3 py-2.5 text-[12.5px]">
                      <span className="text-ink">{a}</span>
                      <span className={t}>{b}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {view === "new" && (
              <div key="new" className="fade-in flex max-w-[680px] flex-col gap-4 p-7 sm:p-14">
                <span className="text-2xl font-medium tracking-tight text-ink">What would you like to check?</span>
                <div className="rounded-xl border border-line2 bg-sf p-3.5">
                  <div className="mb-2.5 inline-flex gap-0.5 rounded-lg border border-line p-[3px] text-[13px]">
                    <span className="rounded-md bg-hover px-3 py-1 text-ink">Text or link</span>
                    <span className="px-3 py-1 text-ink2">Picture, PDF or video</span>
                  </div>
                  <div className="min-h-[110px] text-[15px] text-ink3">Paste a WhatsApp forward, a claim or a news link…</div>
                  <div className="flex items-center justify-between border-t border-line pt-2.5">
                    <span className="text-xs text-ink3">42 checks left this month</span>
                    <button type="button" onClick={() => setView("check")} className="h-8 rounded-lg bg-acc px-3 text-[13px] font-medium text-on-acc hover:bg-acc-h">
                      Check now
                    </button>
                  </div>
                </div>
              </div>
            )}
            {view === "history" && (
              <div key="history" className="fade-in flex flex-col gap-1 p-5 sm:p-7">
                <span className="mb-2.5 text-[1.4rem] font-medium tracking-tight text-ink">History</span>
                <span className="eyebrow px-3 pb-1 text-[10.5px]">Today</span>
                {(
                  [
                    ["Massive lithium reserves discovered in Antarctica", "Picture · 10:15", "False", "false"],
                    ["Govt to pay ₹5,000 a month to every woman", "Forward · 11:42", "False", "false"],
                    ["ISRO's Chandrayaan-3 landed near the south pole", "PDF · 09:03", "True", "true"],
                    ["₹500 notes to be withdrawn from March", "Screenshot · 08:30", "Partly true", "mis"],
                    ["New metro line opens on Monday", "Link · 07:58", "Unconfirmed", "unc"],
                  ] as const
                ).map(([title, meta, verdict, tone]) => (
                  <button key={title} type="button" onClick={() => setView("check")} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors hover:bg-hover">
                    <span className="min-w-0">
                      <span className="block truncate text-[13.5px] text-ink">{title}</span>
                      <span className="block text-[11.5px] text-ink3">{meta}</span>
                    </span>
                    <Tag tone={tone}>{verdict}</Tag>
                  </button>
                ))}
              </div>
            )}
            {view === "usage" && (
              <div key="usage" className="fade-in flex max-w-[720px] flex-col gap-3.5 p-5 sm:p-7">
                <span className="text-[1.4rem] font-medium tracking-tight text-ink">Plan &amp; usage</span>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="flex flex-col gap-1.5 rounded-xl border border-hero-line bg-hero p-4 text-hero-ink">
                    <span className="text-xs text-hero-ink2">Current plan</span>
                    <span className="text-2xl font-medium">Plus</span>
                    <span className="text-[12.5px] text-hero-ink2">₹299 a month · paid until 1 Nov</span>
                  </div>
                  <div className="flex flex-col gap-2 rounded-xl border border-line bg-sf p-4">
                    <span className="text-xs text-ink3">This month</span>
                    <span className="text-2xl font-medium text-ink">
                      78 <span className="text-[13px] font-normal text-ink3">of 120 checks</span>
                    </span>
                    <div className="h-1.5 rounded-full bg-hover">
                      <div className="h-full w-[65%] rounded-full bg-acc-ink" />
                    </div>
                  </div>
                </div>
                <div className="flex items-center justify-between gap-3 rounded-xl border border-line bg-sf p-4">
                  <span>
                    <span className="block text-sm font-medium text-ink">Extra usage</span>
                    <span className="block text-[12.5px] text-ink2">₹{EXTRA_CHECK_INR} a check after 120, up to your ₹300 cap</span>
                  </span>
                  <span className="relative h-6 w-10.5 shrink-0 rounded-full bg-acc" aria-hidden="true">
                    <span className="absolute top-[3px] left-[21px] h-[18px] w-[18px] rounded-full bg-white" />
                  </span>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ---- the laptop: the one animation ---------------------------------------------------

const STEPS = [
  ["Copy, share or paste a forward", "Copy it in WhatsApp and tap the floating Factify button, share a picture or video, or paste it on the website."],
  ["Each claim is pulled out", "The message is split into the separate facts it states, in any of 12 languages."],
  ["Trusted sources are read", "Fact-checkers, wire services, national and regional news, government sites. Unknown sites don't count."],
  ["You get the verdict", "With the line from each source, and a polite correction to send back to the group."],
] as const;
const HOLDS = [2600, 2800, 3200, 5200];

export function HowItWorks() {
  const [step, setStep] = useState(0);
  const [playing, setPlaying] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const schedule = (from: number) => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      const next = (from + 1) % 4;
      setStep(next);
      schedule(next);
    }, HOLDS[from]);
  };

  useEffect(() => {
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) {
      setStep(3);
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setPlaying(true);
          setStep(0);
          schedule(0);
          io.disconnect();
        }
      },
      { threshold: 0.35 },
    );
    if (box.current) io.observe(box.current);
    return () => {
      io.disconnect();
      if (timer.current) clearTimeout(timer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const on = (k: number) => (step >= k ? "on" : "");
  const status = ["Pasted", "Finding claims", "Reading sources", "Done in 24 s"][step];
  const sources: [string, string, "false" | "mis"][] = [
    ["Govt. fact-check unit", "Refutes", "false"],
    ["Wire service", "Refutes", "false"],
    ["National daily", "Refutes", "false"],
    ["State scheme page", "Partly", "mis"],
  ];

  return (
    <div ref={box} className="grid items-center gap-12 lg:grid-cols-[minmax(0,.72fr)_minmax(0,1.28fr)] lg:gap-18">
      <div>
        <span className="eyebrow">How it works</span>
        <h2 className="mt-3.5 text-[2.1rem] leading-[1.08] font-medium tracking-tight text-balance text-ink sm:text-[2.4rem]">From forward to proof, usually in under a minute.</h2>
        <ol className="mt-9 border-b border-line">
          {STEPS.map(([title, body], i) => {
            const active = step === i;
            return (
              <li key={title}>
                <button
                  type="button"
                  aria-pressed={active}
                  onClick={() => {
                    setPlaying(true);
                    setStep(i);
                    schedule(i);
                  }}
                  className={`grid w-full grid-cols-[28px_minmax(0,1fr)] gap-3.5 border-t border-line py-4.5 text-left transition-colors ${active ? "text-ink" : "text-ink3 hover:text-ink2"}`}
                >
                  <span
                    className={`flex h-7 w-7 items-center justify-center rounded-full border font-mono text-xs transition-colors ${
                      active ? "border-acc bg-acc text-on-acc" : step > i ? "border-acc-ink/50 text-acc-ink" : "border-line2"
                    }`}
                  >
                    {i + 1}
                  </span>
                  <span className="min-w-0">
                    <span className="block text-[17px] font-medium tracking-tight">{title}</span>
                    <span className={`grid transition-[grid-template-rows,opacity] duration-500 ${active ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0"}`}>
                      <span className="overflow-hidden">
                        <span className="block pt-1.5 text-[14.5px] leading-relaxed text-ink2">{body}</span>
                      </span>
                    </span>
                    {active && playing && (
                      <span className="mt-3 block h-px overflow-hidden bg-line2">
                        <span key={`${i}-${step}`} className="lap-prog block h-full bg-acc-ink" style={{ ["--dur" as string]: `${HOLDS[i]}ms` }} />
                      </span>
                    )}
                  </span>
                </button>
              </li>
            );
          })}
        </ol>
      </div>

      <div role="img" aria-label="An illustration: a forward is checked on a laptop, its claims are found, trusted sources are read, and the verdict is shown">
        <div className="lap-lid">
          <div className="grid aspect-[16/10] grid-cols-[46px_minmax(0,1fr)] overflow-hidden rounded-md bg-bg text-xs">
            <div className="flex flex-col items-center gap-3.5 border-r border-side-line bg-side pt-3.5">
              <svg width="18" height="18" viewBox="0 0 32 32" fill="none" className="text-acc-ink" aria-hidden="true">
                <circle cx="16" cy="16" r="14.5" stroke="currentColor" strokeWidth="2" />
                <path d="M10.8 16.6l3.5 3.5 7.2-7.6" stroke="currentColor" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <span className="h-6.5 w-6.5 rounded-[7px] bg-acc-soft" />
              <span className="h-6.5 w-6.5 rounded-[7px] bg-hover" />
              <span className="h-6.5 w-6.5 rounded-[7px] bg-hover" />
            </div>
            <div className="flex min-w-0 flex-col gap-3 px-4 py-3.5">
              <div className="flex items-center justify-between">
                <span className="text-[13px] font-medium text-ink">New check</span>
                <span className={`inline-flex items-center gap-1.5 font-mono text-[10.5px] ${step === 3 ? "text-acc-ink" : "text-ink2"}`}>
                  <span className={`h-1.5 w-1.5 rounded-full ${step === 3 ? "bg-acc-ink" : "bg-ink2"}`} />
                  {status}
                </span>
              </div>
              <div className="grid min-h-0 flex-1 grid-cols-2 gap-3.5">
                <div className="flex min-w-0 flex-col gap-3">
                  <div className={`lap-in on rounded-[10px] border border-line2 bg-sf px-3 py-2.5 leading-relaxed text-ink2`}>
                    <div className="mb-1 text-[10px] text-ink3">Forwarded many times</div>
                    The government will pay{" "}
                    <span className={`lap-u ${on(1)}`} style={{ backgroundImage: "linear-gradient(var(--false),var(--false))" }}>
                      ₹5,000 every month
                    </span>{" "}
                    to{" "}
                    <span className={`lap-u ${on(1)}`} style={{ backgroundImage: "linear-gradient(var(--mis),var(--mis))" }}>
                      every woman
                    </span>{" "}
                    from 1 July. Register at the link below.
                    <div className="mt-1.5 font-mono text-[10px] text-ink3">govt-yojana-apply.in/register</div>
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <span className={`lap-in ${on(1)} font-mono text-[9.5px] tracking-[0.12em] text-ink3`}>2 CLAIMS FOUND</span>
                    <div className={`lap-in ${on(1)} flex items-start gap-2 rounded-lg border border-false/30 bg-false-soft/50 px-2.5 py-2 delay-75`}>
                      <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-false" />
                      <span className="text-ink">Govt pays ₹5,000 a month</span>
                    </div>
                    <div className={`lap-in ${on(1)} flex items-start gap-2 rounded-lg border border-mis/30 bg-mis-soft/50 px-2.5 py-2 delay-200`}>
                      <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-mis" />
                      <span className="text-ink">…to every woman, from 1 July</span>
                    </div>
                  </div>
                </div>
                <div className="flex min-w-0 flex-col gap-2">
                  <span className={`lap-in ${on(2)} font-mono text-[9.5px] tracking-[0.12em] text-ink3`}>SOURCES READ</span>
                  <div className="flex flex-col gap-0.5">
                    {sources.map(([name, stance, tone], i) => (
                      <div key={name} className={`lap-in ${on(2)} grid h-7.5 grid-cols-[16px_minmax(0,1fr)_auto] items-center gap-2 px-2`} style={{ transitionDelay: `${80 + i * 120}ms` }}>
                        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" className="text-acc-ink" aria-hidden="true">
                          <circle cx="8" cy="8" r="7" fill="currentColor" fillOpacity=".15" />
                          <path d="M5 8.2l2 2 4-4.2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                        <span className="truncate text-ink">{name}</span>
                        <Tag tone={tone}>{stance}</Tag>
                      </div>
                    ))}
                    <div className={`lap-in ${on(2)} grid h-7.5 grid-cols-[16px_minmax(0,1fr)_auto] items-center gap-2 px-2 text-ink3`} style={{ transitionDelay: "560ms" }}>
                      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" className="text-false" aria-hidden="true">
                        <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeOpacity=".6" strokeDasharray="2 2" />
                      </svg>
                      <span className="truncate line-through">Unknown blog</span>
                      <span className="text-[10.5px]">Not trusted</span>
                    </div>
                  </div>
                  <div className={`lap-in ${on(3)} mt-auto rounded-[10px] border border-false/40 bg-linear-to-b from-false-soft to-sf px-3 py-2.5`}>
                    <div className="flex items-baseline justify-between">
                      <span className="text-2xl font-medium tracking-tight text-false">False</span>
                      <span className="text-[11px] text-false">89% confidence</span>
                    </div>
                    <div className="mt-0.5 text-[11px] leading-snug text-ink2">No national scheme pays this. The link collects phone numbers.</div>
                    <div className="mt-2 flex gap-1.5">
                      <span className="inline-flex h-6 items-center rounded-md bg-acc px-2.5 text-[11px] font-medium text-on-acc">Copy correction</span>
                      <span className="inline-flex h-6 items-center rounded-md border border-line2 px-2.5 text-[11px] text-ink">See sources</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div className="lap-base" />
        <p className="mt-4 text-center text-[13px] text-ink3">An illustration. Real checks show the actual sources read and the time taken.</p>
      </div>
    </div>
  );
}

// ---- features ----------------------------------------------------------------------

const FEATURES = [
  {
    name: "Messages",
    title: "Forwards and claims",
    body: "A forward often mixes something true with something false. Factify splits it into each fact it states and checks them one by one.",
    points: ["Each claim gets its own answer", "Published fact-checks are found first", "English, Hindi and ten more Indian languages"],
  },
  {
    name: "Links",
    title: "News links",
    body: "Factify reads the article behind a link, checks what it says, and tells you about the website it came from.",
    points: ["How old the website is", "Whether it's on our trusted list", "The same answer as pasting the article"],
  },
  {
    name: "Pictures",
    title: "Pictures and screenshots",
    body: "Text in a picture is read and checked like any message. The picture itself is checked for signs it was made by AI.",
    points: ["Reads text in screenshots", "AI-made picture check", "Location data removed before checking"],
  },
  {
    name: "Videos",
    title: "Videos",
    body: "What's said in a video is turned into text and checked. Frames are checked for AI-made pictures, and the voice for signs of cloning.",
    points: ["Speech checked, with the moment it was said", "Cloned-voice and AI-frame checks", "Speech in the first 3 minutes, frames in the first 90 seconds · uses 3 checks"],
  },
  {
    name: "PDFs",
    title: "PDFs and circulars",
    body: "Circulars and notices are read page by page, including scanned ones, and every claim inside is checked.",
    points: ["Scanned pages read too", "Each claim shown with its page", "Files up to 25 MB"],
  },
];

function FeatureVisual({ i }: { i: number }) {
  const card = "rounded-xl border border-line2 bg-sf shadow-[0_20px_40px_-24px_rgba(0,0,0,.45)]";
  if (i === 0)
    return (
      <div className="flex flex-col justify-center gap-4.5 p-8 sm:p-12">
        <div className={`${card} max-w-[420px] self-start rounded-bl-[4px] px-4 py-3.5 text-base leading-relaxed text-ink`}>
          The government will pay <span className="border-b-2 border-false">₹5,000 every month</span> to <span className="border-b-2 border-mis">every woman</span> from 1 July.
        </div>
        <div className="ml-6 flex max-w-[440px] flex-col gap-2.5 text-sm text-ink2">
          <div className="grid grid-cols-[70px_minmax(0,1fr)] gap-2.5">
            <span className="pt-0.5 font-mono text-[11px] text-false">WRONG</span>No national ₹5,000 scheme exists. A government fact-check calls it a scam.
          </div>
          <div className="grid grid-cols-[70px_minmax(0,1fr)] gap-2.5">
            <span className="pt-0.5 font-mono text-[11px] text-mis">PARTLY</span>One state pays some women a monthly amount — not everyone, not ₹5,000.
          </div>
        </div>
      </div>
    );
  if (i === 1)
    return (
      <div className="flex flex-col justify-center p-8 sm:p-12">
        <div className={`${card} overflow-hidden`}>
          <div className="flex h-8.5 items-center gap-2 border-b border-line px-3">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-mis" aria-hidden="true">
              <path d="M12 3l9 16H3z" strokeLinejoin="round" />
            </svg>
            <span className="font-mono text-xs text-ink3">dailyviralnews24.in/lithium-antarctica</span>
          </div>
          <div className="flex flex-col gap-2 p-5">
            <span className="text-[17px] leading-snug font-semibold text-ink">SHOCKING: Massive lithium found in Antarctica, prices to crash</span>
            <span className="text-[13px] text-ink3">By Staff · 2 min read</span>
          </div>
        </div>
        <div className={`${card} relative -mt-4 ml-9 flex max-w-[390px] flex-col gap-2 px-4.5 py-4 text-sm`}>
          <span className="font-medium text-ink">About this website</span>
          {(
            [
              ["On our trusted list", "No", "text-false"],
              ["Registered", "20 days ago", "text-mis"],
              ["Named authors", "None", "text-mis"],
            ] as const
          ).map(([a, b, t]) => (
            <span key={a} className="flex justify-between text-ink2">
              {a}
              <span className={t}>{b}</span>
            </span>
          ))}
        </div>
      </div>
    );
  if (i === 2)
    return (
      <div className="grid items-center gap-4.5 p-8 sm:grid-cols-[minmax(0,1.15fr)_minmax(0,.85fr)] sm:p-10">
        <div className={`${card} p-2`}>
          <svg viewBox="0 0 400 300" className="block w-full rounded-lg" role="img" aria-label="A viral news picture of icebergs with a breaking-news banner">
            <defs>
              <linearGradient id="fsky" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0" stopColor="#0E2236" />
                <stop offset=".55" stopColor="#3E6A86" />
                <stop offset="1" stopColor="#C9E2EC" />
              </linearGradient>
              <linearGradient id="fice" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0" stopColor="#F4FBFF" />
                <stop offset="1" stopColor="#9DC3D4" />
              </linearGradient>
              <linearGradient id="fsea" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0" stopColor="#2B5A73" />
                <stop offset="1" stopColor="#0B2232" />
              </linearGradient>
            </defs>
            <rect width="400" height="300" fill="url(#fsky)" />
            <circle cx="300" cy="70" r="22" fill="#FFE9B8" opacity=".85" />
            <path d="M0 190 L60 120 L95 150 L140 80 L190 145 L230 110 L290 170 L330 130 L400 185 L400 210 L0 210 Z" fill="url(#fice)" />
            <rect y="205" width="400" height="95" fill="url(#fsea)" />
            <ellipse cx="170" cy="190" rx="70" ry="22" fill="#7FFFD1" opacity=".35" />
            <rect y="242" width="400" height="58" fill="#0A0A0A" opacity=".82" />
            <rect x="12" y="250" width="92" height="18" fill="#C8102E" />
            <text x="20" y="263" fontFamily="var(--font-geist), sans-serif" fontSize="11" fontWeight="700" fill="#fff">
              BREAKING NEWS
            </text>
            <text x="12" y="288" fontFamily="var(--font-geist), sans-serif" fontSize="14" fontWeight="600" fill="#fff">
              Massive lithium reserves found in Antarctica
            </text>
          </svg>
        </div>
        <div className="flex flex-col gap-2.5 text-[13px]">
          <div className={`${card} flex flex-col gap-1 px-3.5 py-3`}>
            <span className="text-ink3">Text in the picture</span>
            <span className="text-ink">“Massive lithium reserves found in Antarctica”</span>
          </div>
          <div className={`${card} flex flex-col gap-1.5 px-3.5 py-3`}>
            <span className="text-ink3">AI-made picture check</span>
            <span className="flex justify-between">
              <span className="font-medium text-mis">Likely AI-made</span>
              <span className="text-ink2">strong signal</span>
            </span>
            <span className="h-1 rounded bg-hover">
              <span className="block h-full w-[92%] rounded bg-mis" />
            </span>
          </div>
          <div className={`${card} flex items-center justify-between px-3.5 py-3`}>
            <span className="text-ink2">Verdict</span>
            <Tag tone="false">False</Tag>
          </div>
        </div>
      </div>
    );
  if (i === 3)
    return (
      <div className="flex flex-col justify-center gap-3.5 p-8 sm:p-10">
        <div className={`${card} p-2`}>
          <div className="overflow-hidden rounded-lg">
            <svg viewBox="0 0 640 300" className="block w-full" role="img" aria-label="A video of a speaker at a podium, with subtitles">
              <defs>
                <linearGradient id="fstage" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0" stopColor="#1A2B4A" />
                  <stop offset="1" stopColor="#0B1220" />
                </linearGradient>
                <radialGradient id="fspot" cx=".5" cy=".2" r=".6">
                  <stop offset="0" stopColor="#FFE7B0" stopOpacity=".35" />
                  <stop offset="1" stopColor="#FFE7B0" stopOpacity="0" />
                </radialGradient>
              </defs>
              <rect width="640" height="300" fill="url(#fstage)" />
              <rect width="640" height="300" fill="url(#fspot)" />
              <rect x="40" y="40" width="160" height="90" rx="4" fill="#24406B" opacity=".6" />
              <rect x="440" y="40" width="160" height="90" rx="4" fill="#24406B" opacity=".6" />
              <circle cx="320" cy="108" r="30" fill="#C99A7A" />
              <path d="M290 98 q30 -36 60 0 q-6 -26 -30 -28 q-24 2 -30 28z" fill="#2A1E18" />
              <path d="M262 220 q0 -70 58 -78 q58 8 58 78z" fill="#3B4F6B" />
              <path d="M305 145 l15 30 l15 -30z" fill="#E9EEF5" />
              <rect x="250" y="200" width="140" height="100" rx="6" fill="#5A3B26" />
              <rect x="160" y="236" width="320" height="30" rx="4" fill="#000" opacity=".6" />
              <text x="320" y="256" textAnchor="middle" fontFamily="var(--font-geist), sans-serif" fontSize="14" fill="#fff">
                “…free laptops for every student from June…”
              </text>
            </svg>
            <div className="flex items-center gap-2.5 border-t border-line bg-sf px-2.5 py-2">
              <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" className="text-ink" aria-hidden="true">
                <path d="M4 3l9 5-9 5z" />
              </svg>
              <span className="relative h-1 flex-1 rounded bg-hover">
                <span className="absolute inset-y-0 left-0 w-[48%] rounded bg-ink3" />
                <span className="absolute -top-1 left-[47%] h-3 w-[3px] rounded-sm bg-mis" />
                <span className="absolute -top-1 left-[71%] h-3 w-[3px] rounded-sm bg-acc-ink" />
              </span>
              <span className="font-mono text-[11px] text-ink3">0:42 / 1:28</span>
            </div>
          </div>
        </div>
        <div className="grid grid-cols-3 gap-2.5 text-[12.5px]">
          <div className={`${card} flex flex-col gap-1 px-3 py-2.5`}>
            <span className="text-ink3">Said at 0:42</span>
            <span className="self-start">
              <Tag tone="mis">Misleading</Tag>
            </span>
          </div>
          <div className={`${card} flex flex-col gap-1 px-3 py-2.5`}>
            <span className="text-ink3">Voice</span>
            <span className="font-medium text-acc-ink">No sign of cloning</span>
          </div>
          <div className={`${card} flex flex-col gap-1 px-3 py-2.5`}>
            <span className="text-ink3">Frames</span>
            <span className="font-medium text-acc-ink">Not AI-made</span>
          </div>
        </div>
      </div>
    );
  return (
    <div className="grid items-center gap-7 p-8 sm:grid-cols-[auto_minmax(0,1fr)] sm:p-10">
      <div className="relative mx-auto h-[297px] w-[210px]">
        <div className="absolute top-2.5 left-3.5 h-[297px] w-[210px] rotate-3 rounded bg-[#D9D5CA]" />
        <div className="absolute inset-0 rounded bg-[#F2EFE7] px-5 py-5.5 shadow-[0_18px_40px_-18px_rgba(0,0,0,.5)] [clip-path:polygon(0_0,calc(100%-30px)_0,100%_30px,100%_100%,0_100%)]">
          <div className="flex items-center gap-2 border-b border-[#CFCABD] pb-2.5">
            <span className="h-4.5 w-4.5 rounded-full bg-[#B9893A]" />
            <span className="h-1.5 w-[86px] rounded-sm bg-[#2A2925]" />
          </div>
          <div className="mt-3.5 h-1.5 w-2/5 rounded-sm bg-[#2A2925]" />
          {["100%", "96%"].map((w) => (
            <div key={w} className="mt-2 h-1 rounded-sm bg-[#B8B3A6]" style={{ width: w }} />
          ))}
          <div className="mt-1.5 h-2.5 w-[92%] rounded-sm border-l-2 border-[#C43D2A] bg-[#C43D2A]/30" />
          {["98%", "90%"].map((w) => (
            <div key={w} className="mt-2 h-1 rounded-sm bg-[#B8B3A6]" style={{ width: w }} />
          ))}
          <div className="mt-1.5 h-2.5 w-[78%] rounded-sm border-l-2 border-[#946210] bg-[#946210]/25" />
          {["97%", "60%"].map((w) => (
            <div key={w} className="mt-2 h-1 rounded-sm bg-[#B8B3A6]" style={{ width: w }} />
          ))}
        </div>
        <div className="absolute top-0 right-0 h-7.5 w-7.5 rounded-bl bg-[linear-gradient(225deg,transparent_50%,#CFCABD_50%)]" />
        <span className="absolute bottom-6.5 -left-2.5 inline-flex h-6 items-center rounded-[5px] bg-[#D93A2B] px-2 text-[11px] font-bold tracking-wide text-white">PDF</span>
      </div>
      <div className="flex flex-col gap-2.5">
        <div className={`${card} flex items-center gap-2.5 px-3.5 py-3`}>
          <svg width="28" height="34" viewBox="0 0 28 34" aria-hidden="true">
            <path d="M2 2h17l7 7v23H2z" fill="#F2EFE7" stroke="#B8B3A6" />
            <path d="M19 2v7h7" fill="#D9D5CA" stroke="#B8B3A6" />
            <rect x="0" y="18" width="20" height="10" rx="2" fill="#D93A2B" />
            <text x="10" y="26" textAnchor="middle" fontFamily="var(--font-geist), sans-serif" fontSize="7" fontWeight="700" fill="#fff">
              PDF
            </text>
          </svg>
          <span className="min-w-0">
            <span className="block truncate text-[13.5px] text-ink">circular-scholarship-2026.pdf</span>
            <span className="block text-xs text-ink3">3 pages · 1.2 MB</span>
          </span>
        </div>
        <div className={`${card} flex flex-col gap-2 px-3.5 py-3 text-[13px]`}>
          {(
            [
              ["Page 1 · scholarship of ₹50,000", "False", "false"],
              ["Page 1 · last date 15 Oct", "Partly true", "mis"],
              ["Page 2 · ministry name", "True", "true"],
            ] as const
          ).map(([a, b, t]) => (
            <span key={a} className="flex items-center justify-between gap-3">
              <span className="text-ink2">{a}</span>
              <Tag tone={t}>{b}</Tag>
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

export function Features() {
  const [tab, setTab] = useState(0);
  const f = FEATURES[tab];
  return (
    <>
      <div role="tablist" aria-label="Kinds of content" className="mt-10 flex flex-wrap border-b border-line">
        {FEATURES.map((x, i) => (
          <button
            key={x.name}
            type="button"
            role="tab"
            aria-selected={tab === i}
            onClick={() => setTab(i)}
            className={`relative mr-7 h-11 text-[15px] transition-colors after:absolute after:inset-x-0 after:-bottom-px after:h-px after:origin-center after:bg-acc-ink after:transition-transform ${
              tab === i ? "text-ink after:scale-x-100" : "text-ink3 after:scale-x-0 hover:text-ink2"
            }`}
          >
            {x.name}
          </button>
        ))}
      </div>
      <div className="mt-7 grid overflow-hidden rounded-2xl border border-line bg-sf shadow-card lg:grid-cols-[minmax(0,.78fr)_minmax(0,1.22fr)]">
        <div className="flex flex-col gap-4 border-line p-8 sm:p-10 lg:border-r">
          <h3 className="text-2xl font-medium tracking-tight text-ink">{f.title}</h3>
          <p className="text-[15.5px] leading-relaxed text-ink2">{f.body}</p>
          <ul className="mt-2 flex flex-col gap-2.5">
            {f.points.map((p) => (
              <li key={p} className="flex gap-2.5 text-[14.5px] text-ink2">
                {tick()}
                {p}
              </li>
            ))}
          </ul>
        </div>
        <div key={tab} className="fade-in relative min-h-[460px]" style={{ background: "radial-gradient(ellipse at 70% 0%, var(--glow), transparent 60%), var(--sf2)" }}>
          <FeatureVisual i={tab} />
        </div>
      </div>
    </>
  );
}

// ---- pricing -----------------------------------------------------------------------

type Row = { name: string; price: string; per: string; billed: string; blurb: string; cta: string; href: string; limit: string; features: string[]; popular?: boolean };

function personalRow(p: Plan, yearly: boolean): Row {
  return {
    name: p.name,
    price: rupees(perMonth(p, yearly)),
    per: p.monthInr ? "/ month" : "",
    billed: p.monthInr ? (yearly ? `${rupees(p.yearInr)} for a year` : "Paid a month at a time") : "Free forever",
    blurb: p.blurb,
    cta: p.monthInr ? `Get ${p.name}` : "Start free",
    href: p.monthInr ? `/signup?next=${encodeURIComponent("/app/credits")}` : "/signup",
    limit: `${p.monthlyChecks} checks a month`,
    features: p.features,
    popular: p.popular,
  };
}

export function Pricing() {
  const [team, setTeam] = useState(false);
  const [yearly, setYearly] = useState(false);
  const rows: Row[] = team
    ? [
        {
          name: TEAM.name,
          price: rupees(perMonth(TEAM, yearly)),
          per: "/ member / month",
          billed: `${yearly ? "Paid a year at a time" : "Paid a month at a time"} · from ${TEAM.minSeats} members`,
          blurb: TEAM.blurb,
          cta: "Start a team",
          href: `/signup?next=${encodeURIComponent("/app/org/new")}`,
          limit: `${TEAM.monthlyChecks} checks per member, pooled`,
          features: TEAM.features,
          popular: true,
        },
        {
          name: "API",
          price: rupees(API_CHECK_INR),
          per: "/ check",
          billed: "Pay as you go · billed monthly",
          blurb: "For apps, platforms and moderation tools.",
          cta: "Get an API key",
          href: `/signup?next=${encodeURIComponent("/app/org/new")}`,
          limit: "No monthly minimum",
          features: ["Same answers as the app", "A monthly limit per key, 60 requests a minute", "Usage by key", "Key rotation and IP allow-lists"],
        },
        {
          name: "Enterprise",
          price: "Custom",
          per: "",
          billed: "Agreed with you by email",
          blurb: "For large newsrooms and platforms.",
          cta: "Email us",
          href: "mailto:aswin.aswin5640@gmail.com?subject=Factify%20Enterprise",
          limit: "Volume you need",
          features: ["Everything in Team", "A price for your volume", "Members join by your verified email domain", "Questions answered by email"],
        },
      ]
    : PERSONAL.map((p) => personalRow(p, yearly));

  const seg = (on: boolean) => `rounded-[7px] px-3.5 py-1.5 text-sm transition-colors ${on ? "bg-hover text-ink" : "text-ink2 hover:text-ink"}`;
  return (
    <>
      <div className="flex flex-wrap items-end justify-between gap-6">
        <div>
          <span className="eyebrow">Pricing</span>
          <h2 className="mt-3.5 text-[2.2rem] leading-[1.08] font-medium tracking-tight text-ink sm:text-[2.75rem]">Simple plans, fair limits.</h2>
          <p className="mt-3 max-w-[520px] text-lg leading-relaxed text-ink2">Every plan checks just as carefully. Paid plans give you more checks each month, and you can add more when you need them.</p>
        </div>
        <div className="flex flex-wrap gap-2.5">
          <div role="tablist" aria-label="Who it's for" className="inline-flex rounded-[10px] border border-line p-[3px]">
            <button type="button" role="tab" aria-selected={!team} onClick={() => setTeam(false)} className={seg(!team)}>
              Individual
            </button>
            <button type="button" role="tab" aria-selected={team} onClick={() => setTeam(true)} className={seg(team)}>
              Teams
            </button>
          </div>
          <div role="tablist" aria-label="Billing" className="inline-flex rounded-[10px] border border-line p-[3px]">
            <button type="button" role="tab" aria-selected={!yearly} onClick={() => setYearly(false)} className={seg(!yearly)}>
              Monthly
            </button>
            <button type="button" role="tab" aria-selected={yearly} onClick={() => setYearly(true)} className={seg(yearly)}>
              Yearly <span className="text-acc-ink">−17%</span>
            </button>
          </div>
        </div>
      </div>

      <div className="mt-10 grid gap-4 md:grid-cols-3">
        {rows.map((r) => (
          <div
            key={r.name}
            className={`flex flex-col gap-5 rounded-2xl border p-7 shadow-card transition-colors ${
              r.popular ? "border-acc-ink/40 bg-linear-to-b from-hi to-sf to-45%" : "border-line bg-sf hover:border-line2"
            }`}
          >
            <div className="flex h-5.5 items-center justify-between">
              <span className="text-base font-medium text-ink">{r.name}</span>
              {r.popular && <Tag tone="true">Most popular</Tag>}
            </div>
            <div>
              <div className="flex items-baseline gap-1.5">
                <span className="tabular text-[2.5rem] font-medium tracking-tight text-ink">{r.price}</span>
                <span className="text-sm text-ink3">{r.per}</span>
              </div>
              <div className="mt-0.5 min-h-5 text-[13px] text-ink3">{r.billed}</div>
            </div>
            <p className="min-h-11 text-[14.5px] leading-relaxed text-ink2">{r.blurb}</p>
            <Link
              href={r.href}
              className={`flex h-10 items-center justify-center rounded-[9px] text-sm font-medium transition-colors ${
                r.popular ? "bg-acc text-on-acc hover:bg-acc-h" : "border border-line2 text-ink hover:bg-hover"
              }`}
            >
              {r.cta}
            </Link>
            <div className="h-px bg-line" />
            <ul className="flex flex-col gap-2.5">
              <li className="text-[14.5px] font-medium text-ink">{r.limit}</li>
              {r.features.map((x) => (
                <li key={x} className="flex gap-2.5 text-sm leading-snug text-ink2">
                  {tick("text-ink3")}
                  {x}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-line bg-sf px-7 py-5.5 shadow-card">
        <span>
          <span className="block text-[15.5px] font-medium text-ink">Extra usage</span>
          <span className="block text-sm text-ink2">On any paid plan, keep checking past your limit at ₹{EXTRA_CHECK_INR} a check, with a monthly cap if you want one.</span>
        </span>
        <Link href="/#faq" className="group inline-flex items-center gap-1.5 text-[15px] text-acc-ink">
          How it works {arrow}
        </Link>
      </div>
      <p className="mt-4 text-[13px] text-ink3">
        Prices in Indian rupees; the price shown is the amount you pay. Plans don&apos;t renew by themselves: pay again to continue, or the plan stops at the end of the month or year
        you paid for. A video uses 3 checks. A check that fails costs nothing.
      </p>
    </>
  );
}

/** Where to get the app, said for the screen you're on. */
export function DownloadHere() {
  const [where, setWhere] = useState("");
  useEffect(() => setWhere(`${window.location.host}/download`), []);
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-[15px] font-medium text-ink">On a computer? Open this on your phone:</span>
      <span className="self-start rounded-lg border border-line2 bg-sf px-3 py-1.5 font-mono text-[13px] text-ink">{where || "/download"}</span>
    </div>
  );
}
