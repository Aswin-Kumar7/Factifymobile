"use client";

import Script from "next/script";
import { use, useCallback, useEffect, useState } from "react";
import { useAccount } from "@/components/account";
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

type RazorpayResult = { razorpay_order_id: string; razorpay_payment_id: string; razorpay_signature: string };
declare global {
  interface Window {
    Razorpay?: new (options: Record<string, unknown>) => { open: () => void; on: (e: string, f: (r: unknown) => void) => void };
  }
}

export default function Billing({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { org, reload } = useOrg(id);
  const { refresh } = useAccount();
  const [packs, setPacks] = useState<Packs | null>(null);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [buying, setBuying] = useState<string | null>(null);
  const [message, setMessage] = useState<{ tone: "success" | "error"; text: string } | null>(null);

  const load = useCallback(async () => {
    setPayments(await api<Payment[]>(`/v1/orgs/${id}/billing/payments`, { account: "personal" }).catch(() => []));
  }, [id]);
  useEffect(() => {
    api<Packs>("/v1/billing/packs").then(setPacks).catch(() => undefined);
    load();
  }, [load]);

  if (!org) return <Spinner />;
  if (org.my_role !== "owner") return <Notice tone="info">Only owners can see billing.</Notice>;

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
      <PageTitle eyebrow={org.name} title="Billing" sub="Buy credit packs for the whole organisation. No subscription." />
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
        <Stat label="Credits available" value={n(org.balance - org.held)} />
        <Stat label="Used this month" value={n(org.month_spend)} />
      </div>

      {!packs ? (
        <Spinner />
      ) : !packs.available ? (
        <Notice tone="info">Payments aren&apos;t set up on this server. Email us and we&apos;ll add credits by invoice.</Notice>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {packs.packs.map((p) => (
            <Card key={p.id} className="flex flex-col">
              <div className="font-semibold text-ink">{p.name}</div>
              <div className="mt-2 font-serif text-3xl text-ink">{n(p.credits)}</div>
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

      <h2 className="mt-10 mb-3 font-serif text-2xl text-ink">Payments</h2>
      {payments.length === 0 ? (
        <p className="text-sm text-ink3">No payments yet.</p>
      ) : (
        <Card className="p-0 sm:p-0">
          <Table head={["Date", "Pack", "Credits", "Amount", "Status", ""]}>
            {payments.map((p) => (
              <tr key={p.id}>
                <td className="whitespace-nowrap text-ink2">{when(p.paid_at || p.created_at)}</td>
                <td className="text-ink capitalize">{p.pack}</td>
                <td className="text-ink2">{n(p.credits)}</td>
                <td className="whitespace-nowrap text-ink2">{inr(p.amount_paise / 100)}</td>
                <td>
                  <div className="flex gap-1.5">
                    <Badge tone={p.status === "paid" ? "acc" : p.status === "failed" ? "bad" : "neutral"}>
                      {p.status === "created" ? "Not paid" : p.status === "paid" ? "Paid" : "Failed"}
                    </Badge>
                    {p.test_mode && <Badge tone="warn">Test</Badge>}
                  </div>
                </td>
                <td className="text-right">
                  {p.status === "paid" && (
                    <a
                      href={`/api/f/v1/orgs/${id}/billing/payments/${p.id}/invoice`}
                      target="_blank"
                      rel="noopener"
                      className="text-sm font-semibold text-acc-ink"
                    >
                      Invoice
                    </a>
                  )}
                </td>
              </tr>
            ))}
          </Table>
        </Card>
      )}
    </>
  );
}
