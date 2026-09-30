"use client";

import { use, useEffect, useState } from "react";
import { AreaChart, daily } from "@/components/charts";
import { Card, PageTitle, Select, Spinner, Stat, Table } from "@/components/ui";
import { api, Usage } from "@/lib/api";
import { n, when } from "@/lib/format";
import { useOrg } from "@/lib/use-org";

const reasons: Record<string, string> = {
  check: "Check",
  purchase: "Bought",
  grant: "Added by Factify",
  refund: "Refund",
  adjustment: "Adjustment",
};

export default function UsagePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { org } = useOrg(id);
  const [days, setDays] = useState(30);
  const [usage, setUsage] = useState<Usage | null>(null);

  useEffect(() => {
    setUsage(null);
    api<Usage>(`/v1/orgs/${id}/usage?days=${days}`, { account: "personal" }).then(setUsage).catch(() => undefined);
  }, [id, days]);

  if (!org) return <Spinner />;
  const owner = org.my_role === "owner";
  const total = (usage?.by_day ?? []).reduce((s, d) => s + Number(d.credits), 0);
  const checks = (usage?.by_day ?? []).reduce((s, d) => s + Number(d.checks), 0);
  const series = daily(usage?.by_day ?? [], days);

  return (
    <>
      <PageTitle
        eyebrow={org.name}
        title="Usage"
        sub={owner ? `Everything ${org.name} spent.` : "What you spent in this organisation."}
        action={
          <>
            <Select value={days} onChange={(e) => setDays(Number(e.target.value))} className="w-auto" aria-label="Period">
              <option value={7}>Last 7 days</option>
              <option value={30}>Last 30 days</option>
              <option value={90}>Last 90 days</option>
            </Select>
            <a
              href={`/api/f/v1/orgs/${id}/usage?days=${days}&format=csv`}
              className="inline-flex h-11 items-center rounded-xl border border-line bg-sf px-4 font-semibold text-ink hover:bg-sf2"
            >
              Export CSV
            </a>
          </>
        }
      />
      {!usage ? (
        <Spinner />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 sm:gap-4">
            <Stat label="Credits used" value={n(total)} />
            <Stat label="Checks" value={n(checks)} />
          </div>
          <Card className="mt-6">
            <h2 className="mb-4 font-serif text-2xl text-ink">By day</h2>
            <AreaChart data={series} />
          </Card>
          {owner && (
            <div className="mt-6 grid gap-4 lg:grid-cols-2">
              <Card className="p-0 sm:p-0">
                <h2 className="px-4 pt-4 font-semibold text-ink sm:px-5">By member</h2>
                <Table head={["Member", "Checks", "Credits"]}>
                  {usage.by_member.map((m) => (
                    <tr key={m.user_id}>
                      <td className="max-w-[220px] truncate text-ink">{m.email}</td>
                      <td className="text-ink2">{n(m.checks)}</td>
                      <td className="text-ink2">{n(m.credits)}</td>
                    </tr>
                  ))}
                </Table>
              </Card>
              <Card className="p-0 sm:p-0">
                <h2 className="px-4 pt-4 font-semibold text-ink sm:px-5">By API key</h2>
                <Table head={["Key", "Checks", "Credits"]}>
                  {usage.by_key.map((k) => (
                    <tr key={k.key_id}>
                      <td className="text-ink">
                        {k.name} <span className="font-mono text-xs text-ink3">{k.prefix}…</span>
                      </td>
                      <td className="text-ink2">{n(k.checks)}</td>
                      <td className="text-ink2">{n(k.credits)}</td>
                    </tr>
                  ))}
                </Table>
              </Card>
            </div>
          )}
          <Card className="mt-6 p-0 sm:p-0">
            <h2 className="px-4 pt-4 font-semibold text-ink sm:px-5">Ledger</h2>
            <Table head={["When", "What", "Who", "Credits"]}>
              {usage.ledger.map((l, i) => (
                <tr key={i}>
                  <td className="whitespace-nowrap text-ink2">{when(l.created_at, true)}</td>
                  <td className="text-ink">
                    {reasons[l.reason] ?? l.reason}
                    {l.note && <span className="text-ink3"> · {l.note}</span>}
                  </td>
                  <td className="max-w-[220px] truncate text-ink2">{l.key_name ? `key “${l.key_name}”` : l.email || "—"}</td>
                  <td className={`font-semibold whitespace-nowrap ${l.delta > 0 ? "text-true" : "text-ink"}`}>
                    {l.delta > 0 ? "+" : ""}
                    {n(l.delta)}
                  </td>
                </tr>
              ))}
            </Table>
          </Card>
        </>
      )}
    </>
  );
}
