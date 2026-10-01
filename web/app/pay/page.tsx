"use client";

// Buying credits: from the dashboard, or opened from the phone app with a one-time
// link (?h=…), which signs the person in once and then disappears from the address
// bar. The app waits on its own screen and moves on when this payment is paid,
// fails or is cancelled.

import Link from "next/link";
import Script from "next/script";
import { useRouter } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { ThemeButton } from "@/components/theme";
import { Badge, Button, Notice, Seal, Spinner } from "@/components/ui";
import { api, ApiFailure, authAction, Me, MyOrg } from "@/lib/api";
import { inr, n } from "@/lib/format";

type Pack = { id: string; name: string; credits: number; price_inr: number };
type Packs = { packs: Pack[]; personal_packs: Pack[]; available: boolean; test_mode: boolean };
type Order = { order_id: string; key_id: string; amount: number; currency: string; name: string; description: string; prefill: { email: string } };
type RazorpayResult = { razorpay_order_id: string; razorpay_payment_id: string; razorpay_signature: string };
declare global {
  interface Window {
    Razorpay?: new (options: Record<string, unknown>) => { open: () => void; on: (e: string, f: (r: unknown) => void) => void };
  }
}

function PayPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [orgs, setOrgs] = useState<MyOrg[]>([]);
  const [packs, setPacks] = useState<Packs | null>(null);
  const [account, setAccount] = useState("personal");
  const [chosen, setChosen] = useState<string | null>(null);
  const [handoff, setHandoff] = useState<string | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "paying" | "paid" | "cancelled" | "error">("loading");
  const [message, setMessage] = useState<string | null>(null);
  const [added, setAdded] = useState(0);

  const load = useCallback(async () => {
    const [who, mine, list] = await Promise.all([
      api<Me>("/v1/me", { account: "personal" }),
      api<MyOrg[]>("/v1/orgs", { account: "personal" }).catch(() => [] as MyOrg[]),
      api<Packs>("/v1/billing/packs"),
    ]);
    setMe(who);
    setOrgs(mine.filter((o) => o.role === "owner"));
    setPacks(list);
  }, []);

  useEffect(() => {
    (async () => {
      const params = new URLSearchParams(window.location.search);
      const token = params.get("h");
      try {
        if (token) {
          // Never left in the address bar or the history.
          window.history.replaceState(null, "", "/pay");
          const opened = (await authAction("handoff", { token })) as { handoff_id: string; org_id: string | null };
          setHandoff(opened.handoff_id);
          if (opened.org_id) setAccount(opened.org_id);
          try {
            sessionStorage.setItem("fct_handoff", JSON.stringify(opened));
          } catch {}
          // The app asked to choose a plan rather than buy a pack.
          if (params.get("then") === "plans") {
            router.replace(opened.org_id ? `/app/org/${opened.org_id}/billing` : "/app/credits");
            return;
          }
        } else {
          try {
            const saved = JSON.parse(sessionStorage.getItem("fct_handoff") || "null");
            if (saved?.handoff_id) {
              setHandoff(saved.handoff_id);
              if (saved.org_id) setAccount(saved.org_id);
            }
          } catch {}
          const org = params.get("org");
          if (org) setAccount(org);
        }
        await load();
        setState("ready");
      } catch (e) {
        if (e instanceof ApiFailure && e.status === 401 && !token) {
          router.replace("/signin?next=/pay");
          return;
        }
        setMessage(e instanceof ApiFailure && e.status === 410 ? "This payment link has expired or was already used. Start again from the Factify app." : (e as Error).message);
        setState("error");
      }
    })();
  }, [load, router]);

  const org = orgs.find((o) => o.id === account) ?? null;
  const list = useMemo(() => (org ? packs?.packs : packs?.personal_packs) ?? [], [org, packs]);
  const pack = list.find((p) => p.id === chosen) ?? list[Math.min(1, list.length - 1)];
  const balance = org ? org.balance : (me?.credits.balance ?? 0);

  async function pay() {
    if (!pack) return;
    setState("paying");
    setMessage(null);
    try {
      const order = org
        ? await api<Order>(`/v1/orgs/${org.id}/billing/orders`, { method: "POST", json: { pack: pack.id, handoff_id: handoff }, account: "personal" })
        : await api<Order>("/v1/me/billing/orders", { method: "POST", json: { pack: pack.id, handoff_id: handoff }, account: "personal" });
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
        handler: async (r: RazorpayResult) => {
          try {
            await api(org ? `/v1/orgs/${org.id}/billing/confirm` : "/v1/me/billing/confirm", {
              method: "POST",
              json: { order_id: r.razorpay_order_id, payment_id: r.razorpay_payment_id, signature: r.razorpay_signature },
              account: "personal",
            });
          } catch {
            // Razorpay's webhook confirms it too; the credits still arrive.
          }
          setAdded(pack.credits);
          await load().catch(() => undefined);
          try {
            sessionStorage.removeItem("fct_handoff");
          } catch {}
          setState("paid");
        },
        modal: { ondismiss: () => setState("ready") },
      });
      checkout.on("payment.failed", () => setMessage("That payment didn't go through. Nothing was charged; try again or choose another way to pay."));
      checkout.open();
    } catch (e) {
      setMessage((e as Error).message);
      setState("ready");
    }
  }

  async function cancel() {
    if (handoff) await api(`/v1/billing/handoff/${handoff}/finish`, { method: "POST", json: { status: "cancelled" }, account: "personal" }).catch(() => undefined);
    try {
      sessionStorage.removeItem("fct_handoff");
    } catch {}
    setState("cancelled");
  }

  return (
    <div className="min-h-dvh bg-bg">
      <Script src="https://checkout.razorpay.com/v1/checkout.js" strategy="afterInteractive" />
      <header className="border-b border-line">
        <div className="mx-auto flex h-16 max-w-3xl items-center justify-between px-4 sm:px-6">
          <Link href={handoff ? "#" : "/app/credits"} className="flex items-center gap-2 text-[17px] font-semibold tracking-tight text-ink">
            <Seal size={24} /> Factify
          </Link>
          <ThemeButton />
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-4 py-8 sm:px-6 sm:py-12">
        {state === "loading" && (
          <p className="flex items-center gap-2 py-20 text-ink2">
            <Spinner /> Opening your account…
          </p>
        )}

        {state === "error" && (
          <div className="rounded-[16px] border border-line bg-sf p-6 text-center shadow-card sm:p-10">
            <h1 className="font-medium tracking-tight text-3xl text-ink">Can&apos;t open this payment</h1>
            <p className="mt-3 text-ink2">{message}</p>
          </div>
        )}

        {state === "paid" && (
          <div className="fade-in rounded-[16px] border border-line bg-sf p-6 text-center shadow-lift sm:p-10">
            <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-acc-soft text-3xl text-acc-ink">✓</div>
            <h1 className="font-medium tracking-tight mt-5 text-4xl text-ink">Payment complete</h1>
            <p className="mt-3 text-lg text-ink2">
              {n(added)} credits were added to {org ? org.name : "your account"}. You now have {n(balance)}.
            </p>
            {handoff ? (
              <p className="mt-6 rounded-[14px] bg-sf2 p-4 text-ink">You can close this tab and go back to the Factify app. It has updated already.</p>
            ) : (
              <Link href={org ? `/app/org/${org.id}/billing` : "/app/credits"} className="mt-6 inline-block rounded-[9px] bg-acc px-5 py-3 font-semibold text-on-acc">
                Back to the dashboard
              </Link>
            )}
          </div>
        )}

        {state === "cancelled" && (
          <div className="rounded-[16px] border border-line bg-sf p-6 text-center shadow-card sm:p-10">
            <h1 className="font-medium tracking-tight text-3xl text-ink">Cancelled</h1>
            <p className="mt-3 text-ink2">Nothing was charged. {handoff ? "You can close this tab and go back to the app." : ""}</p>
          </div>
        )}

        {(state === "ready" || state === "paying") && me && packs && (
          <div className="fade-in">
            <div className="text-xs font-semibold tracking-[0.12em] text-acc-ink uppercase">Buy credits</div>
            <h1 className="mt-1 text-4xl leading-tight font-medium tracking-tight text-ink sm:text-5xl">Choose a pack</h1>
            <p className="mt-2 text-ink2">
              Signed in as {me.email}. One check is one credit; a video is three. Credits don&apos;t expire.
            </p>

            {orgs.length > 0 && (
              <div className="mt-6">
                <div className="mb-2 text-sm font-semibold text-ink2">Buying for</div>
                <div className="flex flex-wrap gap-2">
                  {[{ id: "personal", name: "Me (personal)" }, ...orgs.map((o) => ({ id: o.id, name: o.name }))].map((a) => (
                    <button
                      key={a.id}
                      onClick={() => {
                        setAccount(a.id);
                        setChosen(null);
                      }}
                      className={`rounded-full border px-4 py-2 text-sm font-semibold ${account === a.id ? "border-acc bg-acc-soft text-acc-ink" : "border-line bg-sf text-ink2"}`}
                    >
                      {a.name}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="mt-6 grid gap-3 sm:grid-cols-2">
              {list.map((p) => {
                const on = pack?.id === p.id;
                return (
                  <button
                    key={p.id}
                    onClick={() => setChosen(p.id)}
                    aria-pressed={on}
                    className={`rounded-[14px] border p-5 text-left transition-shadow ${on ? "border-acc bg-sf shadow-lift ring-1 ring-acc" : "border-line bg-sf shadow-card hover:border-ink3"}`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-ink">{p.name}</span>
                      {on && <Badge tone="acc">Selected</Badge>}
                    </div>
                    <div className="font-medium tracking-tight tabular mt-3 text-4xl text-ink">{n(p.credits)}</div>
                    <div className="text-sm text-ink3">credits</div>
                    <div className="mt-3 flex items-baseline justify-between">
                      <span className="text-lg font-semibold text-ink">{inr(p.price_inr)}</span>
                      <span className="text-xs text-ink3">₹{(p.price_inr / p.credits).toFixed(2)} a check</span>
                    </div>
                  </button>
                );
              })}
            </div>

            {pack && (
              <div className="mt-6 rounded-[16px] border border-line bg-sf p-5 shadow-card sm:p-6">
                <div className="text-sm font-semibold text-ink2">Summary</div>
                <dl className="mt-3 space-y-2 text-[15px]">
                  <div className="flex justify-between gap-4"><dt className="text-ink2">Account</dt><dd className="text-right text-ink">{org ? org.name : "Personal"}</dd></div>
                  <div className="flex justify-between gap-4"><dt className="text-ink2">Credits now</dt><dd className="tabular text-ink">{n(balance)}</dd></div>
                  <div className="flex justify-between gap-4"><dt className="text-ink2">{pack.name}</dt><dd className="tabular text-ink">+{n(pack.credits)}</dd></div>
                  <div className="flex justify-between gap-4"><dt className="text-ink2">Credits after</dt><dd className="tabular font-semibold text-ink">{n(balance + pack.credits)}</dd></div>
                  <div className="flex justify-between gap-4 border-t border-line pt-3 text-lg"><dt className="font-semibold text-ink">Total</dt><dd className="tabular font-semibold text-ink">{inr(pack.price_inr)}</dd></div>
                </dl>
                {packs.test_mode && (
                  <div className="mt-4">
                    <Notice tone="warning">Test mode: no real money moves. Use Razorpay&apos;s test card 5267 3181 8797 5449, any future date, CVV and OTP.</Notice>
                  </div>
                )}
                {message && (
                  <div className="mt-4">
                    <Notice tone="error">{message}</Notice>
                  </div>
                )}
                <Button size="lg" className="mt-5 w-full" onClick={pay} busy={state === "paying"} disabled={!packs.available}>
                  Pay {inr(pack.price_inr)}
                </Button>
                {!packs.available && <p className="mt-2 text-center text-sm text-ink3">Payments aren&apos;t set up on this server.</p>}
                <button onClick={cancel} className="mt-3 w-full rounded-xl py-2 text-sm font-semibold text-ink3 hover:text-ink">
                  {handoff ? "Cancel and go back to the app" : "Cancel"}
                </button>
                <p className="mt-2 text-center text-xs text-ink3">Payments by Razorpay: UPI, cards and net banking. We never see your card or bank details.</p>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}

export default function Page() {
  return (
    <Suspense>
      <PayPage />
    </Suspense>
  );
}
