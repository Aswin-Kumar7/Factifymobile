"use client";

// An organisation's plan: Team (300 checks a member a month, from three members),
// API (every check paid at the end of the month), or credit packs only. The owner
// subscribes, cancels, turns extra usage on with a cap, or moves to pay-per-check.

import { useCallback, useEffect, useState } from "react";
import { Badge, Button, Notice, Spinner } from "./ui";
import { api } from "@/lib/api";
import { inr, n } from "@/lib/format";
import { API_CHECK_INR, perMonth, rupees, TEAM } from "@/lib/plans";
import { appHandoff, forgetHandoff, payForSubscription, Subscription } from "@/lib/razorpay";

type OrgPlanState = {
  plan: "credits" | "team" | "api";
  seats: number;
  interval: "month" | "year" | null;
  renews_at: string | null;
  cancel_at_end: boolean;
  renewal?: "auto" | "manual" | null;
  allowance: number;
  used: number;
  resets_at: string | null;
  credits: number;
  checks_left: number;
  extra: { enabled: boolean; cap_paise: number | null; used_paise: number; price_paise: number; blocked: boolean };
  bills: { id: string; month: string; checks: number; amount_paise: number; status: string; short_url: string | null }[];
};

const day = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" }) : "—");

export function OrgPlan({ id, members, onChange }: { id: string; members: number; onChange: () => void }) {
  const [state, setState] = useState<OrgPlanState | null>(null);
  const [seats, setSeats] = useState(Math.max(TEAM.minSeats ?? 3, members));
  const [yearly, setYearly] = useState(false);
  const [cap, setCap] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ tone: "success" | "error" | "info"; text: string } | null>(null);

  const load = useCallback(async () => {
    const s = await api<OrgPlanState>(`/v1/orgs/${id}/plan`, { account: "personal" });
    setState(s);
    setCap(s.extra.cap_paise != null ? String(s.extra.cap_paise / 100) : "");
  }, [id]);
  useEffect(() => {
    load().catch((e: Error) => setMessage({ tone: "error", text: e.message }));
  }, [load]);

  async function act(name: string, work: () => Promise<string | null>) {
    setBusy(name);
    setMessage(null);
    try {
      const text = await work();
      if (text) setMessage({ tone: "success", text });
      await load();
      onChange();
    } catch (e) {
      setMessage({ tone: "error", text: (e as Error).message });
    } finally {
      setBusy(null);
    }
  }

  const subscribe = () =>
    act("team", async () => {
      const handoff = appHandoff(id);
      const sub = await api<Subscription>(`/v1/orgs/${id}/plan/subscribe`, {
        method: "POST",
        json: { interval: yearly ? "year" : "month", seats, handoff_id: handoff },
        account: "personal",
      });
      const paid = await payForSubscription(sub);
      if (!paid) return null;
      await api(`/v1/orgs/${id}/plan/confirm`, {
        method: "POST",
        json: paid,
        account: "personal",
      });
      if (handoff) forgetHandoff();
      return `Team is on: ${n(seats * TEAM.monthlyChecks)} checks a month for the organisation.${handoff ? " You can go back to the Factify app now." : ""}`;
    });

  if (!state)
    return message ? (
      <Notice tone={message.tone}>{message.text}</Notice>
    ) : (
      <div className="flex items-center gap-2 py-6 text-ink2">
        <Spinner /> Loading the plan…
      </div>
    );

  const onTeam = state.plan === "team" && state.allowance > 0;
  const manual = onTeam && state.renewal === "manual";
  const paidPlan = state.plan === "team" || state.plan === "api";
  const share = state.allowance ? Math.min(1, state.used / state.allowance) : 0;

  return (
    <div className="flex flex-col gap-4">
      {message && <Notice tone={message.tone}>{message.text}</Notice>}
      <div className="grid gap-4 lg:grid-cols-2">
        <section className="flex flex-col gap-3.5 rounded-[14px] border border-hero-line bg-hero p-5.5 text-hero-ink shadow-card">
          <div className="flex items-start justify-between">
            <div>
              <div className="text-[13px] text-hero-ink2">Plan</div>
              <div className="mt-0.5 text-[1.6rem] font-medium tracking-tight">{onTeam ? `Team · ${n(state.seats)} members` : state.plan === "api" ? "API · pay per check" : "Credit packs"}</div>
            </div>
            {onTeam && (
              <span className={`rounded-md px-2 py-0.5 text-xs font-medium ${state.cancel_at_end && !manual ? "bg-mis-soft text-mis" : "bg-hero-acc/15 text-hero-acc"}`}>
                {manual ? "Paid" : state.cancel_at_end ? "Ending" : "Active"}
              </span>
            )}
          </div>
          <p className="text-[14.5px] leading-relaxed text-hero-ink2">
            {onTeam ? (
              <>
                {n(state.allowance)} checks a month, pooled · {manual ? "paid until" : state.cancel_at_end ? "ends on" : "renews on"} {day(state.renews_at)}
                {manual && (
                  <>
                    <br />
                    It doesn&apos;t renew by itself: pay again to continue, or the organisation goes back to its credits then.
                  </>
                )}
              </>
            ) : state.plan === "api" ? (
              <>Every check is billed at {rupees(API_CHECK_INR)} after the month ends, up to your cap. Credits the organisation holds are used first.</>
            ) : (
              <>The organisation pays from credits it has bought. Move to Team for a monthly pool, or to pay-per-check for the API.</>
            )}
          </p>
          {onTeam && !state.cancel_at_end && !manual && (
            <button
              type="button"
              disabled={!!busy}
              onClick={() => confirm(`Cancel Team? It stays until ${day(state.renews_at)}.`) && act("cancel", async () => {
                  await api(`/v1/orgs/${id}/plan/cancel`, { method: "POST", account: "personal" });
                  return "Cancelled at the end of the period.";
                })}
              className="self-start text-sm text-hero-ink2 underline-offset-4 hover:text-hero-ink hover:underline disabled:opacity-60"
            >
              Cancel Team
            </button>
          )}
          {(state.plan !== "team" || manual) && (
            <button
              type="button"
              disabled={!!busy}
              onClick={() => act("api", async () => {
                  await api(`/v1/orgs/${id}/plan/api`, { method: "PUT", json: { enabled: state.plan !== "api" }, account: "personal" });
                  return null;
                })}
              className="self-start text-sm text-hero-ink2 underline-offset-4 hover:text-hero-ink hover:underline disabled:opacity-60"
            >
              {state.plan === "api" ? "Stop paying per check" : `Pay per check instead (${rupees(API_CHECK_INR)} a check)`}
            </button>
          )}
        </section>

        <section className="flex flex-col gap-3.5 rounded-[14px] border border-line bg-sf p-5.5 shadow-card">
          <div className="flex items-baseline justify-between">
            <h3 className="text-[15px] font-medium text-ink">This month</h3>
            <span className="text-[13px] text-ink3">Resets on {state.resets_at ? new Date(state.resets_at).toLocaleDateString("en-IN", { day: "numeric", month: "short" }) : "the 1st"}</span>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="tabular text-[2.4rem] leading-none font-medium tracking-tight text-ink">{n(state.used)}</span>
            <span className="text-[15px] text-ink3">of {n(state.allowance)} plan checks</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-hover">
            <div className="h-full rounded-full bg-acc-ink" style={{ width: `${Math.max(2, share * 100)}%` }} />
          </div>
          <div className="grid grid-cols-2 gap-2.5 text-[13px] text-ink2">
            <span>
              <span className="tabular block text-[17px] font-medium text-ink">{n(Math.max(state.credits, 0))}</span>credits besides
            </span>
            <span>
              <span className="tabular block text-[17px] font-medium text-ink">{inr(state.extra.used_paise / 100)}</span>extra usage so far
            </span>
          </div>
        </section>
      </div>

      {(!onTeam || manual) && (
        <section className="flex flex-col gap-4 rounded-[14px] border border-acc-ink/30 bg-hi p-5.5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="text-base font-medium text-ink">{manual ? "Pay for the next period" : "Team plan"}</h3>
              <p className="mt-0.5 text-sm text-ink2">
                {n(TEAM.monthlyChecks)} checks a member each month, in one pool. From {TEAM.minSeats} members.
              </p>
            </div>
            <div role="tablist" aria-label="Billing" className="inline-flex rounded-[9px] border border-line bg-sf p-[3px]">
              {[false, true].map((y) => (
                <button
                  key={String(y)}
                  type="button"
                  role="tab"
                  aria-selected={yearly === y}
                  onClick={() => setYearly(y)}
                  className={`rounded-[7px] px-3 py-1.5 text-[13px] ${yearly === y ? "bg-hover text-ink" : "text-ink2 hover:text-ink"}`}
                >
                  {y ? "Yearly −17%" : "Monthly"}
                </button>
              ))}
            </div>
          </div>
          <div className="flex flex-wrap items-end gap-5">
            <label className="flex w-32 flex-col gap-1.5">
              <span className="text-[13px] text-ink2">Members</span>
              <input
                type="number"
                min={TEAM.minSeats}
                value={seats}
                onChange={(e) => setSeats(Math.max(TEAM.minSeats ?? 3, Number(e.target.value) || 0))}
                className="h-10.5 rounded-[9px] border border-line2 bg-sf px-3 text-[14.5px] text-ink focus:border-acc-ink focus:outline-none"
              />
            </label>
            <span className="flex flex-col gap-0.5">
              <span className="text-[13px] text-ink2">{yearly ? "A year" : "A month"}</span>
              <span className="tabular text-[17px] font-medium text-ink">
                {rupees(seats * (yearly ? TEAM.yearInr : TEAM.monthInr))}
                <span className="ml-1 text-[13px] font-normal text-ink3">({rupees(perMonth(TEAM, yearly))} a member a month)</span>
              </span>
            </span>
            <span className="flex flex-col gap-0.5">
              <span className="text-[13px] text-ink2">Checks a month</span>
              <span className="tabular text-[17px] font-medium text-ink">{n(seats * TEAM.monthlyChecks)}</span>
            </span>
            <Button onClick={subscribe} busy={busy === "team"} disabled={!!busy}>
              {manual ? "Pay" : "Start Team"}
            </Button>
          </div>
        </section>
      )}

      {paidPlan && (
        <section className="flex flex-col gap-3 rounded-[14px] border border-line bg-sf p-5.5 shadow-card">
          <div className="flex items-start justify-between gap-5">
            <div>
              <h3 className="text-base font-medium text-ink">Extra usage {state.plan === "api" && <Badge tone="acc">Always on</Badge>}</h3>
              <p className="mt-1 max-w-xl text-sm leading-relaxed text-ink2">
                Checks past the plan and the credits, at {rupees(state.extra.price_paise / 100)} a check, billed once after the month ends - never past the cap.
              </p>
            </div>
            {state.plan === "team" && (
              <button
                type="button"
                role="switch"
                aria-checked={state.extra.enabled}
                aria-label="Extra usage"
                disabled={!!busy}
                onClick={() => act("extra", async () => {
                    await api(`/v1/orgs/${id}/plan/extra`, { method: "PUT", json: { enabled: !state.extra.enabled, cap_inr: cap === "" ? null : Number(cap) }, account: "personal" });
                    return null;
                  })}
                className={`relative h-6 w-10.5 shrink-0 rounded-full transition-colors ${state.extra.enabled ? "bg-acc" : "bg-line2"}`}
              >
                <span className={`absolute top-[3px] h-[18px] w-[18px] rounded-full bg-white shadow transition-[left] ${state.extra.enabled ? "left-[21px]" : "left-[3px]"}`} />
              </button>
            )}
          </div>
          {state.extra.blocked && <Notice tone="warning">Last month&apos;s bill is unpaid, so extra usage is paused until it&apos;s paid.</Notice>}
          {state.extra.enabled && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                act("cap", async () => {
                  await api(`/v1/orgs/${id}/plan/extra`, { method: "PUT", json: { enabled: true, cap_inr: cap === "" ? null : Number(cap) }, account: "personal" });
                  return "Saved.";
                });
              }}
              className="flex flex-wrap items-end gap-4 border-t border-line pt-4"
            >
              <label className="flex w-44 flex-col gap-1.5">
                <span className="text-[13px] text-ink2">Monthly cap (₹)</span>
                <input
                  type="number"
                  min={0}
                  step={100}
                  value={cap}
                  onChange={(e) => setCap(e.target.value)}
                  placeholder="No cap"
                  className="h-10.5 rounded-[9px] border border-line2 bg-sf px-3 text-[14.5px] text-ink focus:border-acc-ink focus:outline-none"
                />
              </label>
              <Button type="submit" variant="outline" busy={busy === "cap"}>
                Save cap
              </Button>
            </form>
          )}
          {state.bills.length > 0 && (
            <ul className="divide-y divide-line border-t border-line text-sm">
              {state.bills.map((b) => (
                <li key={b.id} className="flex items-center justify-between gap-3 py-2.5">
                  <span className="text-ink">
                    {new Date(b.month).toLocaleDateString("en-IN", { month: "long", year: "numeric" })} · {n(b.checks)} checks
                  </span>
                  <span className="flex items-center gap-3">
                    <span className="tabular text-ink2">{inr(b.amount_paise / 100)}</span>
                    {b.status === "paid" ? (
                      <Badge tone="acc">Paid</Badge>
                    ) : b.short_url ? (
                      <a href={b.short_url} target="_blank" rel="noopener" className="font-medium text-acc-ink">
                        Pay
                      </a>
                    ) : (
                      <Badge>{b.status}</Badge>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}
