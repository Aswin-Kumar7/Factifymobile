"use client";

// Plan & usage: your monthly plan, this month's checks, extra usage, changing or
// cancelling the plan, and what you have paid. Everything shown is read from the
// server (GET /v1/me/plan); paying goes through Razorpay Checkout.

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useAccount } from "@/components/account";
import { Badge, Button, Card, Notice, PageTitle, Spinner, Table } from "@/components/ui";
import { api } from "@/lib/api";
import { inr, n, when } from "@/lib/format";
import { PERSONAL, perMonth, rupees } from "@/lib/plans";
import { appHandoff, forgetHandoff, payForSubscription, Subscription } from "@/lib/razorpay";

type Sub = { id: string; plan: string; interval: string; status: string; kind?: string; amount_paise: number; current_end: string | null; created_at: string; test_mode: boolean };
type Bill = { id: string; month: string; checks: number; amount_paise: number; status: string; short_url: string | null };
type MyPlan = {
  plan: "free" | "plus" | "pro";
  name: string;
  interval: "month" | "year" | null;
  renews_at: string | null;
  cancel_at_end: boolean;
  // "auto": renews by itself; "manual": paid a month or a year at a time.
  renewal?: "auto" | "manual" | null;
  allowance: number;
  used: number;
  resets_at: string | null;
  credits: number;
  checks_left: number;
  extra: { enabled: boolean; cap_paise: number | null; used_paise: number; price_paise: number; blocked: boolean };
  subscriptions: Sub[];
  bills: Bill[];
};
type Payment = { id: string; pack: string; credits: number; amount_paise: number; status: string; test_mode: boolean; created_at: string; paid_at: string | null };

const shortDate = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" }) : "—");

export default function PlanAndUsage() {
  const { me, refresh } = useAccount();
  const [plan, setPlan] = useState<MyPlan | null>(null);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [yearly, setYearly] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ tone: "success" | "error" | "info"; text: string } | null>(null);
  const [cap, setCap] = useState("");
  // Sent here by the phone app to choose a plan: it is waiting to hear back.
  const [fromApp, setFromApp] = useState<string | null>(null);
  useEffect(() => setFromApp(appHandoff()), []);

  const load = useCallback(async () => {
    const [p, pays] = await Promise.all([
      api<MyPlan>("/v1/me/plan", { account: "personal" }),
      api<Payment[]>("/v1/me/billing/payments", { account: "personal" }).catch(() => [] as Payment[]),
    ]);
    setPlan(p);
    setPayments(pays);
    setCap(p.extra.cap_paise != null ? String(p.extra.cap_paise / 100) : "");
  }, []);

  useEffect(() => {
    load().catch((e: Error) => setMessage({ tone: "error", text: e.message }));
  }, [load]);

  async function subscribe(planId: string) {
    setBusy(planId);
    setMessage(null);
    try {
      const sub = await api<Subscription>("/v1/me/plan/subscribe", {
        method: "POST",
        json: { plan: planId, interval: yearly ? "year" : "month", handoff_id: fromApp },
        account: "personal",
      });
      const paid = await payForSubscription(sub);
      if (!paid) {
        setMessage({ tone: "info", text: "Nothing was charged." });
        return;
      }
      await api("/v1/me/plan/confirm", {
        method: "POST",
        json: paid,
        account: "personal",
      });
      setMessage({ tone: "success", text: fromApp ? "You're on the new plan. You can go back to the Factify app now." : "You're on the new plan. Its checks are yours from now." });
      if (fromApp) {
        forgetHandoff();
        setFromApp(null);
      }
      await Promise.all([load(), refresh()]);
    } catch (e) {
      setMessage({ tone: "error", text: (e as Error).message });
    } finally {
      setBusy(null);
    }
  }

  async function cancel() {
    if (!plan || !confirm(`Cancel ${plan.name}? You keep it until ${shortDate(plan.renews_at)}, then you're on Free.`)) return;
    setBusy("cancel");
    try {
      await api("/v1/me/plan/cancel", { method: "POST", account: "personal" });
      setMessage({ tone: "info", text: `Cancelled. ${plan.name} stays until ${shortDate(plan.renews_at)}.` });
      await load();
    } catch (e) {
      setMessage({ tone: "error", text: (e as Error).message });
    } finally {
      setBusy(null);
    }
  }

  async function saveExtra(enabled: boolean) {
    setBusy("extra");
    try {
      const capInr = cap.trim() === "" ? null : Math.max(0, Math.round(Number(cap)));
      await api("/v1/me/plan/extra", { method: "PUT", json: { enabled, cap_inr: capInr }, account: "personal" });
      await Promise.all([load(), refresh()]);
    } catch (e) {
      setMessage({ tone: "error", text: (e as Error).message });
    } finally {
      setBusy(null);
    }
  }

  if (!me) return null;
  if (!plan)
    return (
      <div className="flex items-center gap-2 py-16 text-ink2">
        <Spinner /> Loading your plan…
      </div>
    );

  const paid = plan.plan !== "free";
  const manual = paid && plan.renewal === "manual";
  const left = Math.max(plan.allowance - plan.used, 0);
  const share = plan.allowance ? Math.min(1, plan.used / plan.allowance) : 0;
  const current = PERSONAL.find((p) => p.id === plan.plan) ?? PERSONAL[0];
  const extraChecks = plan.extra.price_paise ? Math.round(plan.extra.used_paise / plan.extra.price_paise) : 0;
  const capChecks = plan.extra.cap_paise != null && plan.extra.price_paise ? Math.floor(plan.extra.cap_paise / plan.extra.price_paise) : null;
  const paidPacks = payments.filter((p) => p.status === "paid");
  // A plan paid a month (or a year) at a time stops on its date unless paid again.
  const daysLeft = manual && plan.renews_at ? Math.ceil((new Date(plan.renews_at).getTime() - Date.now()) / 86_400_000) : null;
  const lastPaid = plan.subscriptions.find((s) => s.current_end);
  const endedOn = !paid && lastPaid?.current_end && new Date(lastPaid.current_end) < new Date() ? lastPaid : null;
  const planName = (id: string) => PERSONAL.find((p) => p.id === id)?.name ?? id;

  return (
    <div className="flex flex-col gap-4">
      <PageTitle title="Plan & usage" sub="Your plan, how much you've used, and what happens when you run out." />
      {fromApp && !message && <Notice tone="info">Choose a plan below. When it&apos;s paid, the Factify app on your phone will know.</Notice>}
      {message && <Notice tone={message.tone}>{message.text}</Notice>}
      {daysLeft != null && daysLeft <= 5 && (
        <Notice tone="warning">
          Your {plan.name} plan ends {daysLeft <= 0 ? "today" : daysLeft === 1 ? "tomorrow" : `in ${daysLeft} days`}, on {shortDate(plan.renews_at)}. To keep it, pay for another{" "}
          {plan.interval === "year" ? "year" : "month"} below; otherwise you&apos;ll move to Free.
        </Notice>
      )}
      {endedOn && (
        <Notice tone="info">
          Your {planName(endedOn.plan)} plan ended on {shortDate(endedOn.current_end)}, so you&apos;re on Free now. Pay for {planName(endedOn.plan)} again below to continue.
        </Notice>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {/* The plan, as the app's dark feature card */}
        <section className="flex flex-col gap-4 rounded-[14px] border border-hero-line bg-hero p-5.5 text-hero-ink shadow-card">
          <div className="flex items-start justify-between">
            <div>
              <div className="text-[13px] text-hero-ink2">Current plan</div>
              <div className="mt-0.5 text-[1.75rem] font-medium tracking-tight">{plan.name}</div>
            </div>
            <span className={`rounded-md px-2 py-0.5 text-xs font-medium ${plan.cancel_at_end && !manual ? "bg-mis-soft text-mis" : "bg-hero-acc/15 text-hero-acc"}`}>
              {manual ? "Paid" : plan.cancel_at_end ? "Ending" : "Active"}
            </span>
          </div>
          <p className="text-[14.5px] leading-relaxed text-hero-ink2">
            {paid ? (
              <>
                {rupees(plan.interval === "year" ? current.yearInr : current.monthInr)} a {plan.interval === "year" ? "year" : "month"} · {n(plan.allowance)} checks a month
                <br />
                {manual ? "Paid until" : plan.cancel_at_end ? "Ends" : "Renews"} {manual ? "" : "on "}
                {shortDate(plan.renews_at)}
                {manual && (
                  <>
                    <br />
                    It doesn&apos;t renew by itself: pay again to continue, or it stops then.
                  </>
                )}
              </>
            ) : (
              <>
                {n(plan.allowance)} checks every month, free.
                <br />
                Upgrade for more checks and extra usage.
              </>
            )}
          </p>
          {paid && !plan.cancel_at_end && !manual && (
            <div>
              <button type="button" onClick={cancel} disabled={busy === "cancel"} className="text-sm text-hero-ink2 underline-offset-4 hover:text-hero-ink hover:underline disabled:opacity-60">
                {busy === "cancel" ? "Cancelling…" : "Cancel plan"}
              </button>
            </div>
          )}
        </section>

        <section className="flex flex-col gap-3.5 rounded-[14px] border border-line bg-sf p-5.5 shadow-card">
          <div className="flex items-baseline justify-between">
            <h2 className="text-[15px] font-medium text-ink">This month</h2>
            <span className="text-[13px] text-ink3">Resets on {plan.resets_at ? new Date(plan.resets_at).toLocaleDateString("en-IN", { day: "numeric", month: "short" }) : "the 1st"}</span>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="tabular text-[2.5rem] leading-none font-medium tracking-tight text-ink">{n(plan.used)}</span>
            <span className="text-[15px] text-ink3">of {n(plan.allowance)} plan checks used</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-hover" role="progressbar" aria-valuenow={plan.used} aria-valuemax={plan.allowance}>
            <div className={`h-full rounded-full ${share >= 0.9 ? "bg-false" : share >= 0.7 ? "bg-mis" : "bg-acc-ink"}`} style={{ width: `${Math.max(2, share * 100)}%` }} />
          </div>
          <div className="grid grid-cols-3 gap-2.5 text-[13px] text-ink2">
            <span>
              <span className="tabular block text-[17px] font-medium text-ink">{n(left)}</span>left on the plan
            </span>
            <span>
              <span className="tabular block text-[17px] font-medium text-ink">{n(Math.max(plan.credits, 0))}</span>credits besides
            </span>
            <span>
              <span className="tabular block text-[17px] font-medium text-ink">{n(extraChecks)}</span>extra checks
            </span>
          </div>
          <p className="text-xs text-ink3">A video uses 3 checks; anything else, 1. A check that fails costs nothing.</p>
        </section>
      </div>

      {/* Extra usage */}
      <section className="flex flex-col gap-4 rounded-[14px] border border-line bg-sf p-5.5 shadow-card">
        <div className="flex items-start justify-between gap-5">
          <div>
            <h2 className="text-base font-medium text-ink">Extra usage</h2>
            <p className="mt-1 max-w-xl text-[14.5px] leading-relaxed text-ink2">
              Keep checking after your plan&apos;s checks run out, at {rupees(plan.extra.price_paise / 100 || 3)} a check. You&apos;re sent one bill after the month ends,
              never more than your cap.
            </p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={plan.extra.enabled}
            aria-label="Extra usage"
            disabled={!paid || busy === "extra"}
            onClick={() => saveExtra(!plan.extra.enabled)}
            className={`relative h-6 w-10.5 shrink-0 rounded-full transition-colors disabled:opacity-50 ${plan.extra.enabled ? "bg-acc" : "bg-line2"}`}
          >
            <span className={`absolute top-[3px] h-[18px] w-[18px] rounded-full bg-white shadow transition-[left] ${plan.extra.enabled ? "left-[21px]" : "left-[3px]"}`} />
          </button>
        </div>
        {!paid && <p className="text-[13px] text-ink3">Extra usage comes with Plus and Pro.</p>}
        {plan.extra.blocked && <Notice tone="warning">Last month&apos;s extra usage bill is unpaid, so extra usage is paused until it&apos;s paid.</Notice>}
        {paid && plan.extra.enabled && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              saveExtra(true);
            }}
            className="flex flex-wrap items-end gap-6 border-t border-line pt-4"
          >
            <label className="flex w-40 flex-col gap-1.5">
              <span className="text-[13px] text-ink2">Monthly cap (₹)</span>
              <input
                type="number"
                min={0}
                step={50}
                value={cap}
                onChange={(e) => setCap(e.target.value)}
                placeholder="No cap"
                className="h-10.5 rounded-[9px] border border-line2 bg-sf px-3 text-[14.5px] text-ink focus:border-acc-ink focus:ring-3 focus:ring-acc-ink/15 focus:outline-none"
              />
            </label>
            <span className="flex flex-col gap-0.5">
              <span className="text-[13px] text-ink2">That&apos;s up to</span>
              <span className="text-[17px] font-medium text-ink">{capChecks == null ? "no limit" : `${n(capChecks)} extra checks`}</span>
            </span>
            <span className="flex flex-col gap-0.5">
              <span className="text-[13px] text-ink2">Used so far</span>
              <span className="tabular text-[17px] font-medium text-ink">{inr(plan.extra.used_paise / 100)}</span>
            </span>
            <Button type="submit" variant="outline" busy={busy === "extra"}>
              Save cap
            </Button>
          </form>
        )}
      </section>

      {/* Plans */}
      <section className="flex flex-col gap-4 rounded-[14px] border border-line bg-sf p-5.5 shadow-card">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-base font-medium text-ink">{manual ? "Renew or change plan" : paid ? "Change plan" : "Upgrade"}</h2>
          <div role="tablist" aria-label="Billing" className="inline-flex rounded-[9px] border border-line p-[3px]">
            {[false, true].map((y) => (
              <button
                key={String(y)}
                type="button"
                role="tab"
                aria-selected={yearly === y}
                onClick={() => setYearly(y)}
                className={`rounded-[7px] px-3 py-1.5 text-[13px] transition-colors ${yearly === y ? "bg-hover text-ink" : "text-ink2 hover:text-ink"}`}
              >
                {y ? (
                  <>
                    Yearly <span className="text-acc-ink">−17%</span>
                  </>
                ) : (
                  "Monthly"
                )}
              </button>
            ))}
          </div>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          {PERSONAL.filter((p) => p.id !== "free").map((p) => {
            const same = p.id === plan.plan && (plan.interval === "year") === yearly;
            const mine = same && !manual && !plan.cancel_at_end;
            return (
              <div key={p.id} className={`flex flex-col gap-3 rounded-[12px] border p-4.5 ${p.popular ? "border-acc-ink/35 bg-hi" : "border-line"}`}>
                <div className="flex items-center justify-between">
                  <span className="text-[15px] font-medium text-ink">{p.name}</span>
                  {p.popular && <Badge tone="acc">Most popular</Badge>}
                </div>
                <div className="flex items-baseline gap-1.5">
                  <span className="tabular text-[1.9rem] font-medium tracking-tight text-ink">{rupees(perMonth(p, yearly))}</span>
                  <span className="text-[13px] text-ink3">/ month{yearly ? `, ${rupees(p.yearInr)} a year` : ""}</span>
                </div>
                <div className="text-sm text-ink2">{n(p.monthlyChecks)} checks a month</div>
                <Button variant={p.popular ? "primary" : "outline"} disabled={mine || !!busy} busy={busy === p.id} onClick={() => subscribe(p.id)}>
                  {mine
                    ? "Your plan"
                    : same && manual
                      ? `Pay for another ${yearly ? "year" : "month"}`
                      : p.id === plan.plan
                        ? `Switch to ${yearly ? "yearly" : "monthly"}`
                        : `Get ${p.name}`}
                </Button>
              </div>
            );
          })}
        </div>
        <p className="text-xs text-ink3">
          Prices in rupees, including GST. A plan is paid for a month or a year at a time and starts when the payment goes through. Paying again for the same plan adds the next
          period after the one you have; a different plan replaces it at once. Nothing renews by itself. Need more for a team?{" "}
          <Link href="/app/org/new" className="text-acc-ink">
            Create an organisation
          </Link>
          .
        </p>
      </section>

      {(plan.subscriptions.length > 0 || plan.bills.length > 0 || paidPacks.length > 0) && (
        <Card className="p-0 sm:p-0">
          <div className="flex items-baseline justify-between px-4 pt-4 sm:px-5">
            <h2 className="text-base font-medium text-ink">Billing history</h2>
            <Link href="/pay" className="text-[13px] text-acc-ink">
              Top up with a pack
            </Link>
          </div>
          <Table head={["Date", "Description", "Amount", ""]}>
            {plan.subscriptions.map((s) => (
              <tr key={s.id}>
                <td className="whitespace-nowrap text-ink2">{when(s.created_at)}</td>
                <td className="text-ink">
                  {s.plan === "plus" ? "Plus" : s.plan === "pro" ? "Pro" : s.plan} · {s.interval === "year" ? "yearly" : "monthly"}{" "}
                  <span className="text-ink3">({s.status === "replaced" ? "replaced" : s.status === "cancelling" ? "ending" : s.status})</span> {s.test_mode && <Badge tone="warn">Test</Badge>}
                </td>
                <td className="tabular whitespace-nowrap text-ink2">{inr(s.amount_paise / 100)}</td>
                <td />
              </tr>
            ))}
            {plan.bills.map((b) => (
              <tr key={b.id}>
                <td className="whitespace-nowrap text-ink2">{new Date(b.month).toLocaleDateString("en-IN", { month: "short", year: "numeric" })}</td>
                <td className="text-ink">Extra usage · {n(b.checks)} checks</td>
                <td className="tabular whitespace-nowrap text-ink2">{inr(b.amount_paise / 100)}</td>
                <td className="text-right">
                  {b.status === "paid" ? (
                    <Badge tone="acc">Paid</Badge>
                  ) : b.short_url ? (
                    <a href={b.short_url} target="_blank" rel="noopener" className="text-sm font-medium text-acc-ink">
                      Pay
                    </a>
                  ) : (
                    <Badge>{b.status}</Badge>
                  )}
                </td>
              </tr>
            ))}
            {paidPacks.map((p) => (
              <tr key={p.id}>
                <td className="whitespace-nowrap text-ink2">{when(p.paid_at || p.created_at)}</td>
                <td className="text-ink">
                  {n(p.credits)} credits {p.test_mode && <Badge tone="warn">Test</Badge>}
                </td>
                <td className="tabular whitespace-nowrap text-ink2">{inr(p.amount_paise / 100)}</td>
                <td className="text-right">
                  <a href={`/api/f/v1/me/billing/payments/${p.id}/invoice`} target="_blank" rel="noopener" className="text-sm font-medium text-acc-ink">
                    Invoice
                  </a>
                </td>
              </tr>
            ))}
          </Table>
        </Card>
      )}
    </div>
  );
}
