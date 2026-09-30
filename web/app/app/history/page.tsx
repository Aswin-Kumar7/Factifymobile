"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useAccount } from "@/components/account";
import { VerdictPill, Verdict } from "@/components/result";
import { Button, Empty, PageTitle } from "@/components/ui";
import { api } from "@/lib/api";
import { clearHistory, HistoryItem, readHistory } from "@/lib/history";
import { when } from "@/lib/format";

type Shared = {
  enabled: boolean;
  checks: { case_id: string; title: string | null; verdict: string | null; created_at: string; email: string | null; key_name: string | null }[];
};

function Row({ href, title, verdict, meta }: { href: string; title: string; verdict: string | null; meta: string }) {
  return (
    <li>
      <Link href={href} className="flex items-center gap-3 px-4 py-3.5 hover:bg-sf2">
        <div className="min-w-0 flex-1">
          <div className="truncate font-medium text-ink">{title}</div>
          <div className="truncate text-xs text-ink3">{meta}</div>
        </div>
        {verdict && <VerdictPill verdict={verdict as Verdict["verdict"]} />}
      </Link>
    </li>
  );
}

export default function History() {
  const { current, orgs } = useAccount();
  const [mine, setMine] = useState<HistoryItem[]>([]);
  const [shared, setShared] = useState<Shared | null>(null);

  useEffect(() => setMine(readHistory()), []);
  useEffect(() => {
    setShared(null);
    if (current) api<Shared>(`/v1/orgs/${current.id}/history`).then(setShared).catch(() => undefined);
  }, [current]);

  const name = (account: string) => (account === "personal" ? "Personal" : (orgs.find((o) => o.id === account)?.name ?? "Organisation"));

  return (
    <>
      <PageTitle
        title="History"
        sub="Your checks are kept in this browser only. We don't keep a record of what you check."
        action={
          mine.length > 0 && (
            <Button
              variant="outline"
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
          )
        }
      />

      {current && shared?.enabled && (
        <section className="mb-8">
          <h2 className="mb-3 font-serif text-2xl text-ink">{current.name}&apos;s shared history</h2>
          {shared.checks.length ? (
            <ul className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-sf">
              {shared.checks.map((c) => (
                <Row
                  key={c.case_id + c.created_at}
                  href={`/app/check?case=${c.case_id}`}
                  title={c.title || "A check"}
                  verdict={c.verdict}
                  meta={`${when(c.created_at, true)} · ${c.key_name ? `key “${c.key_name}”` : c.email || ""}`}
                />
              ))}
            </ul>
          ) : (
            <Empty title="No shared checks yet" />
          )}
        </section>
      )}

      <h2 className="mb-3 font-serif text-2xl text-ink">In this browser</h2>
      {mine.length ? (
        <ul className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-sf">
          {mine.map((h) => (
            <Row
              key={h.case_id}
              href={`/app/check?case=${h.case_id}`}
              title={h.title}
              verdict={h.verdict}
              meta={`${when(h.at, true)} · ${name(h.account)}`}
            />
          ))}
        </ul>
      ) : (
        <Empty title="Nothing checked here yet">
          <Link href="/app/check" className="font-semibold text-acc-ink">
            Check something
          </Link>
        </Empty>
      )}
    </>
  );
}
