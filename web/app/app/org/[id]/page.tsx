"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { Bars, Card, Notice, PageTitle, Spinner, Stat } from "@/components/ui";
import { api, Usage } from "@/lib/api";
import { n, roleName } from "@/lib/format";
import { useOrg } from "@/lib/use-org";

export default function Overview({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { org, error } = useOrg(id);
  const [usage, setUsage] = useState<Usage | null>(null);

  useEffect(() => {
    api<Usage>(`/v1/orgs/${id}/usage?days=30`, { account: "personal" }).then(setUsage).catch(() => undefined);
  }, [id]);

  if (error) return <Notice tone="error">{error}</Notice>;
  if (!org) return <Spinner />;

  const owner = org.my_role === "owner";
  const available = org.balance - org.held;
  const days = (() => {
    const map = new Map((usage?.by_day ?? []).map((d) => [d.day, Number(d.credits)]));
    return Array.from({ length: 30 }, (_, i) => {
      const d = new Date(Date.now() - (29 - i) * 86400000).toISOString().slice(0, 10);
      return { label: d.slice(5), value: map.get(d) ?? 0 };
    });
  })();

  return (
    <>
      <PageTitle
        title={org.name}
        sub={
          <>
            You&apos;re {owner ? "an" : "a"} {roleName[org.my_role].toLowerCase()}
            {org.status !== "active" && <> · this organisation is {org.status}</>}
          </>
        }
        action={
          <>
            <Link href="/app/check" className="rounded-xl bg-acc px-4 py-2.5 font-semibold text-on-acc">
              Check something
            </Link>
            {owner && (
              <Link href={`/app/org/${id}/billing`} className="rounded-xl border border-line bg-sf px-4 py-2.5 font-semibold text-ink">
                Buy credits
              </Link>
            )}
          </>
        }
      />

      {org.alerts.length > 0 && (
        <div className="mb-6 space-y-2">
          {org.alerts.map((a) => (
            <Notice key={a.text} tone={a.level}>
              {a.text}
            </Notice>
          ))}
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <Stat label="Credits available" value={n(available)} sub={org.held ? `${n(org.held)} held by running checks` : "in the pool"} />
        <Stat
          label="Used this month"
          value={n(org.month_spend)}
          sub={org.monthly_spend_limit != null ? `of a ${n(org.monthly_spend_limit)} limit` : "no monthly limit"}
        />
        <Stat label="Members" value={n(org.members)} />
        <Stat label="Active API keys" value={n(org.active_keys)} />
      </div>

      {!owner && org.my_monthly_limit != null && (
        <Card className="mt-4">
          <div className="text-sm text-ink2">Your monthly limit here is {n(org.my_monthly_limit)} credits.</div>
        </Card>
      )}

      <Card className="mt-6">
        <div className="mb-4 flex items-baseline justify-between">
          <h2 className="font-serif text-2xl text-ink">{owner ? "Credits used" : "Your credits used"}, last 30 days</h2>
          <Link href={`/app/org/${id}/usage`} className="text-sm font-semibold text-acc-ink">
            Details
          </Link>
        </div>
        {usage ? <Bars data={days} /> : <Spinner />}
      </Card>

      {owner && usage && (
        <div className="mt-6 grid gap-4 lg:grid-cols-2">
          <Card>
            <h2 className="mb-3 font-semibold text-ink">Top members</h2>
            {usage.by_member.length ? (
              <ul className="space-y-2 text-sm">
                {usage.by_member.slice(0, 5).map((m) => (
                  <li key={m.user_id} className="flex justify-between gap-3">
                    <span className="truncate text-ink">{m.email}</span>
                    <span className="shrink-0 text-ink2">{n(m.credits)} credits</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-ink3">No checks yet.</p>
            )}
          </Card>
          <Card>
            <h2 className="mb-3 font-semibold text-ink">Top API keys</h2>
            {usage.by_key.length ? (
              <ul className="space-y-2 text-sm">
                {usage.by_key.slice(0, 5).map((k) => (
                  <li key={k.key_id} className="flex justify-between gap-3">
                    <span className="truncate text-ink">
                      {k.name} <span className="font-mono text-xs text-ink3">{k.prefix}…</span>
                    </span>
                    <span className="shrink-0 text-ink2">{n(k.credits)} credits</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-ink3">No API calls yet.</p>
            )}
          </Card>
        </div>
      )}
    </>
  );
}
