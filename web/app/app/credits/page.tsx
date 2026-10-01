"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useAccount } from "@/components/account";
import { Ring } from "@/components/charts";
import { Icon } from "@/components/shell";
import { Badge, Card, PageTitle, Table } from "@/components/ui";
import { api } from "@/lib/api";
import { inr, n, roleName, when } from "@/lib/format";

type Payment = { id: string; pack: string; credits: number; amount_paise: number; status: string; test_mode: boolean; created_at: string; paid_at: string | null };

export default function Credits() {
  const { me, orgs } = useAccount();
  const [payments, setPayments] = useState<Payment[]>([]);
  useEffect(() => {
    api<Payment[]>("/v1/me/billing/payments", { account: "personal" }).then(setPayments).catch(() => undefined);
  }, []);
  if (!me) return null;
  const paid = payments.filter((p) => p.status === "paid");
  return (
    <>
      <PageTitle
        eyebrow="You"
        title="Credits"
        action={
          <Link href="/pay" className="inline-flex items-center gap-1.5 rounded-xl bg-acc px-4 py-2.5 font-semibold text-on-acc hover:brightness-110">
            <Icon name="plus" size={18} /> Buy credits
          </Link>
        }
      />
      <section className="paper flex flex-col items-start gap-6 rounded-3xl border border-line bg-sf p-6 shadow-card sm:flex-row sm:items-center sm:p-8">
        <Ring used={me.credits.used} total={Math.max(1, me.credits.used + me.credits.balance)} label={n(me.credits.balance)} sub="left" size={148} />
        <div className="min-w-0 flex-1">
          <div className="text-sm font-medium text-ink3">Credits left</div>
          <div className="tabular font-serif text-6xl leading-none font-medium text-ink">{n(me.credits.balance)}</div>
          <p className="mt-3 text-[15px] text-ink2">
            You&apos;ve used {n(me.credits.used)} on {n(me.credits.checks)} checks. The same balance is in the phone app.
          </p>
          <Link href="/pay" className="mt-4 inline-flex rounded-xl border border-line bg-sf px-4 py-2 text-sm font-semibold text-ink hover:bg-sf2">
            Top up from ₹199
          </Link>
        </div>
      </section>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <Card>
          <h2 className="font-semibold text-ink">What a check costs</h2>
          <p className="mt-1 text-[15px] text-ink2">Text, a link, a picture or a PDF: 1 credit. A video: 3. A check that fails costs nothing.</p>
        </Card>
        <Card className="paper">
          <h2 className="font-semibold text-ink">For a team?</h2>
          <p className="mt-1 text-[15px] text-ink2">An organisation plan gives your team one credit pool, limits per person and API keys.</p>
          <Link href="/app/org/new" className="mt-3 inline-block font-semibold text-acc-ink">
            Request an organisation plan →
          </Link>
        </Card>
      </div>

      {paid.length > 0 && (
        <Card className="mt-6 p-0 sm:p-0">
          <h2 className="px-4 pt-4 font-semibold text-ink sm:px-5">Your payments</h2>
          <Table head={["Date", "Pack", "Credits", "Amount", ""]}>
            {paid.map((p) => (
              <tr key={p.id}>
                <td className="whitespace-nowrap text-ink2">{when(p.paid_at || p.created_at)}</td>
                <td className="text-ink">
                  {p.pack.replace(/^p/, "")} credits {p.test_mode && <Badge tone="warn">Test</Badge>}
                </td>
                <td className="tabular text-ink2">+{n(p.credits)}</td>
                <td className="tabular whitespace-nowrap text-ink2">{inr(p.amount_paise / 100)}</td>
                <td className="text-right">
                  <a href={`/api/f/v1/me/billing/payments/${p.id}/invoice`} target="_blank" rel="noopener" className="text-sm font-semibold text-acc-ink">
                    Invoice
                  </a>
                </td>
              </tr>
            ))}
          </Table>
        </Card>
      )}

      {orgs.length > 0 && (
        <Card className="mt-6">
          <h2 className="font-semibold text-ink">Your organisations</h2>
          <ul className="mt-2 divide-y divide-line">
            {orgs.map((o) => (
              <li key={o.id} className="flex flex-wrap items-center justify-between gap-3 py-2.5">
                <Link href={`/app/org/${o.id}`} className="min-w-0 truncate font-medium text-ink hover:underline">
                  {o.name}
                </Link>
                <span className="shrink-0 text-sm text-ink3">
                  {roleName[o.role]} · you used {n(o.my_month_spend)}
                  {o.monthly_limit != null ? ` of ${n(o.monthly_limit)}` : ""} this month
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </>
  );
}
