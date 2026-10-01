"use client";

import Script from "next/script";
import { use, useCallback, useEffect, useState } from "react";
import { useAccount } from "@/components/account";
import { OrgPlan } from "@/components/org-plan";
import { Badge, Button, Card, Notice, PageTitle, Spinner, Stat, Table } from "@/components/ui";
import { api } from "@/lib/api";
import { inr, n, when } from "@/lib/format";
import { useOrg } from "@/lib/use-org";

type Pack = { id: string; name: string; credits: number; price_inr: number };
type Packs = { packs: Pack[]; available: boolean; test_mode: boolean };
type Order = {
  order_id: string;
  key_id: string;
  amount: number;
  currency: string;
  name: string;
  description: string;
  prefill: { email: string };
};
type Payment = {
  id: string;
  pack: string;
  credits: number;
  amount_paise: number;
  status: string;
  test_mode: boolean;
  created_at: string;
  paid_at: string | null;
};

type PlanPayment = { id: string; plan: string; interval: string; seats: number; status: string; amount_paise: number; current_start: string | null; created_at: string; test_mode: boolean; paid?: boolean };
type Bill = { id: string; month: string; checks: number; amount_paise: number; status: string; paid_at: string | null; short_url: string | null; test_mode: boolean };
/** One row of the payments list: a pack, a Team plan payment or an extra usage bill. */
type Row = { key: string; at: string; what: string; amount_paise: number; status: "paid" | "created" | "failed" | "other"; statusText?: string; test: boolean; invoice: string | null; pay?: string | null };

type RazorpayResult = { razorpay_order_id: string; razorpay_payment_id: string; razorpay_signature: string };

export default function Billing({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { org, error, reload } = useOrg(id);
  const { refresh } = useAccount();
  const [packs, setPacks] = useState<Packs | null>(null);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [plans, setPlans] = useState<{ subscriptions: PlanPayment[]; bills: Bill[] }>({ subscriptions: [], bills: [] });
  const [buying, setBuying] = useState<string | null>(null);
  const [message, setMessage] = useState<{ tone: "success" | "error"; text: string } | null>(null);

  const load = useCallback(async () => {
    const [pays, plan] = await Promise.all([
      api<Payment[]>(`/v1/orgs/${id}/billing/payments`, { account: "personal" }).catch(() => [] as Payment[]),
      api<{ subscriptions: PlanPayment[]; bills: Bill[] }>(`/v1/orgs/${id}/plan`, { account: "personal" }).catch(() => ({ subscriptions: [], bills: [] })),
    ]);
    setPayments(pays);
    setPlans({ subscriptions: plan.subscriptions ?? [], bills: plan.bills ?? [] });
  }, [id]);
  useEffect(() => {
    api<Packs>("/v1/billing/packs").then(setPacks).catch(() => undefined);
    load();
  }, [load]);

  if (error) return <Notice tone="error">{error}</Notice>;
  if (!org) return <Spinner />;
  if (org.my_role !== "owner") return <Notice tone="info">Only owners can see billing.</Notice>;

  const base = `/api/f/v1/orgs/${id}/billing`;
  const rows: Row[] = [
    ...payments.map((p) => ({
      key: `pack-${p.id}`,
      at: p.paid_at || p.created_at,
      what: `${p.pack.charAt(0).toUpperCase()}${p.pack.slice(1)} pack · ${n(p.credits)} credits`,
      amount_paise: p.amount_paise,
      status: (p.status === "paid" || p.status === "failed" ? p.status : "created") as Row["status"],
      test: p.test_mode,
      invoice: p.status === "paid" ? `${base}/payments/${p.id}/invoice` : null,
    })),
    ...plans.subscriptions.map((s) => ({
      key: `plan-${s.id}`,
      at: s.current_start || s.created_at,
      what: `Team · ${n(s.seats)} members · ${s.interval === "year" ? "a year" : "a month"}`,
      amount_paise: s.amount_paise,
      status: (s.current_start ? "paid" : s.status === "failed" ? "failed" : "other") as Row["status"],
      statusText: s.current_start ? undefined : s.status,
      test: s.test_mode,
      invoice: s.current_start ? `${base}/plans/${s.id}/invoice` : null,
    })),
    ...plans.bills.map((b) => ({
      key: `bill-${b.id}`,
      at: b.paid_at || b.month,
      what: `Extra usage · ${new Date(b.month).toLocaleDateString("en-IN", { month: "long", year: "numeric" })} · ${n(b.checks)} checks`,
      amount_paise: b.amount_paise,
      status: (b.status === "paid" ? "paid" : b.status === "created" ? "created" : "other") as Row["status"],
      statusText: b.status === "created" || b.status === "paid" ? undefined : b.status,
      test: b.test_mode,
      invoice: b.status === "paid" ? `${base}/bills/${b.id}/invoice` : null,
      pay: b.status === "created" ? b.short_url : null,
    })),
  ].sort((a, b) => (a.at < b.at ? 1 : -1));

  async function buy(pack: Pack) {
    setBuying(pack.id);
    setMessage(null);
    try {
      const order = await api<Order>(`/v1/orgs/${id}/billing/orders`, {
        method: "POST",
        json: { pack: pack.id },
        account: "personal",
      });
      if (!window.Razorpay) throw new Error("The payment window couldn't load. Check your connection and try again.");
      const checkout = new window.Razorpay({
        key: order.key_id,
        order_id: order.order_id,
        amount: order.amount,
        currency: order.currency,
        name: order.name,
        description: order.description,
        prefill: order.prefill,
        theme: { color: "#0E6B4F" },
        handler: async (result: RazorpayResult) => {
          try {
            await api(`/v1/orgs/${id}/billing/confirm`, {
              method: "POST",
              json: {
                order_id: result.razorpay_order_id,
                payment_id: result.razorpay_payment_id,
                signature: result.razorpay_signature,
              },
              account: "personal",
            });
            setMessage({ tone: "success", text: `Paid. ${n(pack.credits)} credits were added to ${org!.name}.` });
          } catch (e) {
            setMessage({
              tone: "error",
              text: `${(e as Error).message}. If you were charged, the credits arrive within a few minutes.`,
            });
          }
          await Promise.all([reload(), load(), refresh()]);
          setBuying(null);
        },
        modal: { ondismiss: () => setBuying(null) },
      });
      checkout.on("payment.failed", () => {
        setMessage({ tone: "error", text: "The payment didn't go through. Nothing was charged." });
        setBuying(null);
      });
      checkout.open();
    } catch (e) {
      setMessage({ tone: "error", text: (e as Error).message });
      setBuying(null);
    }
  }

  return (
    <>
      <Script src="https://checkout.razorpay.com/v1/checkout.js" strategy="afterInteractive" />
      <PageTitle eyebrow={org.name} title="Plan & billing" sub="The Team plan gives the organisation a monthly pool; credit packs top it up, with no subscription." />
      <div className="mb-8">
        <OrgPlan id={id} members={org.members} onChange={() => Promise.all([reload(), refresh(), load()])} />
      </div>
      <h2 className="mb-3 text-lg font-medium text-ink">Credit packs</h2>
      {packs?.test_mode && (
        <div className="mb-4">
          <Notice tone="warning">
            Test mode: no real money moves. Pay with Razorpay&apos;s Indian test card 5267 3181 8797 5449, any future date,
            any CVV and any OTP.
          </Notice>
        </div>
      )}
      {message && (
        <div className="mb-4">
          <Notice tone={message.tone}>{message.text}</Notice>
        </div>
      )}
      <div className="mb-6 grid grid-cols-2 gap-3 sm:gap-4">
        <Stat label="Credits available" value={n(Math.max(org.month.credits, 0))} sub={org.month.allowance > 0 ? `besides ${n(Math.max(org.month.allowance - org.month.plan_used, 0))} plan checks left` : undefined} />
        <Stat label="Used this month" value={n(org.month_spend)} />
      </div>

      {!packs ? (
        <Spinner />
      ) : !packs.available ? (
        <Notice tone="info">Payments aren&apos;t set up on this server, so packs can&apos;t be bought here. Factify&apos;s team can add credits to the organisation from the admin panel.</Notice>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {packs.packs.map((p) => (
            <Card key={p.id} className="flex flex-col">
              <div className="font-semibold text-ink">{p.name}</div>
              <div className="font-medium tracking-tight mt-2 text-3xl text-ink">{n(p.credits)}</div>
              <div className="text-sm text-ink3">credits</div>
              <div className="mt-3 text-lg font-semibold text-ink">{inr(p.price_inr)}</div>
              <div className="text-xs text-ink3">₹{(p.price_inr / p.credits).toFixed(2)} a check</div>
              <Button className="mt-4" onClick={() => buy(p)} busy={buying === p.id} disabled={!!buying}>
                Buy
              </Button>
            </Card>
          ))}
        </div>
      )}

      <h2 className="mt-10 mb-3 text-lg font-medium text-ink">Payments</h2>
      {rows.length === 0 ? (
        <p className="text-sm text-ink3">No payments yet.</p>
      ) : (
        <Card className="p-0 sm:p-0">
          <Table head={["Date", "What", "Amount", "Status", ""]}>
            {rows.map((r) => (
              <tr key={r.key}>
                <td className="whitespace-nowrap text-ink2">{when(r.at)}</td>
                <td className="text-ink">{r.what}</td>
                <td className="whitespace-nowrap text-ink2">{inr(r.amount_paise / 100)}</td>
                <td>
                  <div className="flex gap-1.5">
                    <Badge tone={r.status === "paid" ? "acc" : r.status === "failed" ? "bad" : "neutral"}>
                      {r.statusText ?? (r.status === "created" ? "Not paid" : r.status === "paid" ? "Paid" : "Failed")}
                    </Badge>
                    {r.test && <Badge tone="warn">Test</Badge>}
                  </div>
                </td>
                <td className="text-right">
                  {r.invoice ? (
                    <a href={r.invoice} target="_blank" rel="noopener" className="text-sm font-semibold text-acc-ink">
                      Invoice
                    </a>
                  ) : r.pay ? (
                    <a href={r.pay} target="_blank" rel="noopener" className="text-sm font-semibold text-acc-ink">
                      Pay
                    </a>
                  ) : null}
                </td>
              </tr>
            ))}
          </Table>
          <p className="px-4 pb-4 text-xs text-ink3 sm:px-5">Prices include GST at 18%; each invoice shows the taxable value and the GST.</p>
        </Card>
      )}
    </>
  );
}
