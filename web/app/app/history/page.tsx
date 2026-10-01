"use client";

// History: everything checked in this browser, grouped by day, searchable and
// filtered by verdict; and an organisation's shared history when it keeps one.
// Opening one shows its answer alone (/app/check?case=…). A check still running when
// its page was left is here too, and is asked for its verdict while this is open.

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useAccount } from "@/components/account";
import { headlineOf, labelOf, VerdictPill, Verdict } from "@/components/result";
import { Button, Empty, PageTitle } from "@/components/ui";
import { api, ApiFailure } from "@/lib/api";
import { n, when } from "@/lib/format";
import { clearHistory, FAILED, HistoryItem, PENDING, readHistory, updateHistory } from "@/lib/history";

type Shared = {
  enabled: boolean;
  checks: { case_id: string; title: string | null; verdict: string | null; created_at: string; email: string | null; name?: string | null; input_type?: string | null; key_name: string | null }[];
};

type Filter = "all" | "false" | "partly" | "true" | "unc";

const FILTERS: [Filter, string][] = [
  ["all", "All"],
  ["false", "False"],
  ["partly", "Misleading or partly true"],
  ["true", "True"],
  ["unc", "Unconfirmed"],
];

function matches(f: Filter, verdict: string) {
  if (f === "all") return true;
  if (f === "false") return verdict === "FALSE";
  if (f === "true") return verdict === "TRUE";
  if (f === "partly") return verdict === "PARTLY_TRUE" || verdict === "MISLEADING";
  return verdict === "UNCONFIRMED" || verdict === "NOTHING";
}

const kindTag = { text: "TXT", link: "URL", image: "IMG", pdf: "PDF", video: "VID", file: "FILE" } as const;

// How often a check still running is asked for its verdict while History is open.
const POLL_MS = 5000;

/** Ask the server how each running check is getting on, and keep what it says. */
async function settle(items: HistoryItem[]): Promise<boolean> {
  let changed = false;
  for (const h of items.filter((x) => x.verdict === PENDING)) {
    try {
      const answer = await api<Verdict | { status?: string }>(`/v1/cases/${h.case_id}`);
      if (!(answer as Verdict).verdict) continue; // still running
      const v = answer as Verdict;
      updateHistory(h.case_id, { case_id: v.case_id, verdict: labelOf(v), title: headlineOf(v) || h.title });
      changed = true;
    } catch (failure) {
      // Ended without an answer (refused, failed, stopped), or no longer known. Not
      // when the service could not be reached: it may still be running.
      if (failure instanceof ApiFailure && ![401, 429, 502, 503, 504].includes(failure.status)) {
        updateHistory(h.case_id, { verdict: FAILED });
        changed = true;
      }
    }
  }
  return changed;
}

function dayOf(iso: string) {
  const d = new Date(iso);
  const today = new Date();
  const yesterday = new Date(Date.now() - 86400000);
  if (d.toDateString() === today.toDateString()) return "Today";
  if (d.toDateString() === yesterday.toDateString()) return "Yesterday";
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: d.getFullYear() === today.getFullYear() ? undefined : "numeric" });
}

function Row({ href, tag, title, verdict, meta, time }: { href: string; tag: string; title: string; verdict: string | null; meta: string; time: string }) {
  return (
    <li>
      <Link href={href} className="grid grid-cols-[38px_minmax(0,1fr)_auto] items-center gap-3.5 rounded-[10px] px-3 py-2.5 transition-colors hover:bg-hover sm:grid-cols-[38px_minmax(0,1fr)_auto_64px]">
        <span className="flex h-9.5 w-9.5 items-center justify-center rounded-[10px] border border-line font-mono text-[10.5px] text-ink2">{tag}</span>
        <span className="min-w-0">
          <span className="block truncate text-[14.5px] text-ink">{title}</span>
          <span className="block truncate text-[12.5px] text-ink3">{meta}</span>
        </span>
        {verdict === PENDING ? (
          <span className="inline-flex shrink-0 rounded-md bg-hover px-2 py-0.5 text-xs font-medium text-ink2">Checking…</span>
        ) : verdict === FAILED ? (
          <span className="inline-flex shrink-0 rounded-md bg-hover px-2 py-0.5 text-xs font-medium text-ink3">No answer</span>
        ) : verdict ? (
          <VerdictPill verdict={verdict as Verdict["verdict"] | "NOTHING"} />
        ) : (
          <span />
        )}
        <span className="tabular hidden text-right text-[13px] text-ink3 sm:block">{time}</span>
      </Link>
    </li>
  );
}

export default function History() {
  const { me, current, orgs } = useAccount();
  const [mine, setMine] = useState<HistoryItem[]>([]);
  const [shared, setShared] = useState<Shared | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");

  useEffect(() => setMine(readHistory()), [me?.id]);

  // Checks still running when their page was left: asked now, then every few
  // seconds while any is still running and this page is open.
  const pending = mine.some((h) => h.verdict === PENDING);
  useEffect(() => {
    if (!pending) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const tick = async () => {
      if (await settle(readHistory())) {
        if (alive) setMine(readHistory());
      }
      if (alive) timer = setTimeout(tick, POLL_MS);
    };
    tick();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [pending]);
  useEffect(() => {
    setShared(null);
    if (current) api<Shared>(`/v1/orgs/${current.id}/history`).then(setShared).catch(() => undefined);
  }, [current]);

  const name = (account: string) => (account === "personal" ? "Personal" : (orgs.find((o) => o.id === account)?.name ?? "Organisation"));

  const month = useMemo(() => {
    const start = new Date();
    start.setDate(1);
    start.setHours(0, 0, 0, 0);
    const these = mine.filter((h) => new Date(h.at) >= start);
    return {
      all: these.length,
      false: these.filter((h) => h.verdict === "FALSE").length,
      partly: these.filter((h) => h.verdict === "PARTLY_TRUE" || h.verdict === "MISLEADING").length,
      true: these.filter((h) => h.verdict === "TRUE").length,
    };
  }, [mine]);

  const counts = useMemo(() => Object.fromEntries(FILTERS.map(([f]) => [f, mine.filter((h) => matches(f, h.verdict)).length])), [mine]);

  const groups = useMemo(() => {
    const q = query.trim().toLowerCase();
    const shown = mine.filter((h) => matches(filter, h.verdict) && (!q || h.title.toLowerCase().includes(q)));
    const out: { day: string; rows: HistoryItem[] }[] = [];
    for (const h of shown) {
      const d = dayOf(h.at);
      const g = out.find((x) => x.day === d);
      if (g) g.rows.push(h);
      else out.push({ day: d, rows: [h] });
    }
    return out;
  }, [mine, filter, query]);

  return (
    <div className="flex flex-col gap-6">
      <PageTitle
        title="History"
        sub="Everything you've checked in this browser. Open one to see its claims and evidence."
        action={
          <>
            {mine.length > 0 && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  if (confirm("Clear your history in this browser?")) {
                    clearHistory();
                    setMine([]);
                  }
                }}
              >
                Clear
              </Button>
            )}
            <Link href="/app/check?new=1" className="inline-flex h-9 items-center rounded-[9px] bg-acc px-4 text-sm font-medium text-on-acc hover:bg-acc-h">
              New check
            </Link>
          </>
        }
      />

      {mine.length > 0 && (
        <div className="grid grid-cols-2 overflow-hidden rounded-[14px] border border-line bg-hi sm:grid-cols-4">
          {(
            [
              ["This month", month.all, "text-ink"],
              ["False", month.false, "text-false"],
              ["Misleading or partly true", month.partly, "text-mis"],
              ["True", month.true, "text-true"],
            ] as const
          ).map(([label, value, tone], i) => (
            <div key={label} className={`px-4.5 py-4 ${i ? "border-l border-line" : ""} ${i === 2 ? "max-sm:border-l-0 max-sm:border-t" : ""} ${i === 3 ? "max-sm:border-t" : ""}`}>
              <div className="truncate text-[12.5px] text-ink3">{label}</div>
              <div className={`tabular mt-0.5 text-[1.6rem] font-medium tracking-tight ${tone}`}>{n(value)}</div>
            </div>
          ))}
        </div>
      )}

      {current && shared?.enabled && (
        <section>
          <h2 className="eyebrow mb-2 px-3">{current.name} · shared history</h2>
          {shared.checks.length ? (
            <ul className="flex flex-col gap-0.5">
              {shared.checks.map((c) => (
                <Row
                  key={c.case_id + c.created_at}
                  href={`/app/check?case=${c.case_id}`}
                  tag={kindTag[c.input_type as keyof typeof kindTag] ?? "ORG"}
                  title={c.title || "A check"}
                  verdict={c.verdict}
                  meta={c.key_name ? `API key “${c.key_name}”` : c.name || c.email || ""}
                  time={when(c.created_at)}
                />
              ))}
            </ul>
          ) : (
            <Empty title="No shared checks yet" />
          )}
        </section>
      )}

      {mine.length ? (
        <>
          <div className="flex flex-col gap-3">
            <label className="flex h-10.5 items-center gap-2.5 rounded-[10px] border border-line2 bg-sf px-3.5 transition-shadow focus-within:border-acc-ink focus-within:ring-3 focus-within:ring-acc-ink/15">
              <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" className="text-ink3" aria-hidden="true">
                <circle cx="11" cy="11" r="6.5" />
                <path d="M16 16l4 4" />
              </svg>
              <span className="sr-only">Search your checks</span>
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search your checks"
                className="min-w-0 flex-1 bg-transparent text-[14.5px] text-ink placeholder:text-ink3 focus:outline-none"
              />
            </label>
            <div className="flex flex-wrap gap-2">
              {FILTERS.map(([f, label]) => (
                <button
                  key={f}
                  type="button"
                  onClick={() => setFilter(f)}
                  aria-pressed={filter === f}
                  className={`inline-flex h-8 items-center gap-1.5 rounded-lg border px-3 text-[13px] transition-colors ${
                    filter === f ? "border-acc-ink/35 bg-acc-soft text-ink" : "border-line text-ink2 hover:bg-hover hover:text-ink"
                  }`}
                >
                  {label} <span className="tabular text-[11px] text-ink3">{counts[f]}</span>
                </button>
              ))}
            </div>
          </div>

          {groups.length ? (
            groups.map((g) => (
              <section key={g.day}>
                <h2 className="eyebrow mb-1.5 px-3">{g.day}</h2>
                <ul className="flex flex-col gap-0.5">
                  {g.rows.map((h) => (
                    <Row
                      key={h.case_id}
                      href={`/app/check?case=${h.case_id}${h.kind && h.kind !== "file" ? `&kind=${h.kind}` : ""}`}
                      tag={kindTag[h.kind] ?? "TXT"}
                      title={h.title}
                      verdict={h.verdict}
                      meta={name(h.account)}
                      time={new Date(h.at).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false })}
                    />
                  ))}
                </ul>
              </section>
            ))
          ) : (
            <Empty title="No checks match" />
          )}
        </>
      ) : (
        <Empty title="Nothing checked here yet">
          Your list of checks is kept in this browser only; what you check is stored on our server without your name.{" "}
          <Link href="/app/check?new=1" className="font-medium text-acc-ink">
            Check something
          </Link>
        </Empty>
      )}
    </div>
  );
}
