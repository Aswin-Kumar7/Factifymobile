"use client";

// Razorpay Checkout for a subscription: load its script once, open it on the
// subscription the server made, and resolve with Razorpay's signed result (or null
// when the person closes it). The server checks the signature; this only carries it.

/** What the server started: an auto-renewing subscription, or one order paying for a
 * single month or year (where the Razorpay account has no subscriptions). */
export type Subscription = {
  mode?: "subscription" | "order";
  subscription_id?: string;
  order_id?: string;
  key_id: string;
  amount: number;
  name: string;
  description: string;
  prefill: { email: string };
  test_mode: boolean;
};

/** Checkout's signed result, as the server's confirm endpoints take it. */
type PlanPaid = { payment_id: string; signature: string; subscription_id?: string; order_id?: string };

type Checkout = new (options: Record<string, unknown>) => { open: () => void; on: (e: string, f: (r: unknown) => void) => void };

declare global {
  interface Window {
    Razorpay?: Checkout;
  }
}

let loading: Promise<void> | null = null;

function load(): Promise<void> {
  if (window.Razorpay) return Promise.resolve();
  loading ??= new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.onload = () => resolve();
    script.onerror = () => {
      loading = null;
      reject(new Error("The payment window couldn't load. Check your connection and try again."));
    };
    document.body.appendChild(script);
  });
  return loading;
}

export async function payForSubscription(sub: Subscription): Promise<PlanPaid | null> {
  await load();
  const Razorpay = window.Razorpay!;
  const byOrder = sub.mode === "order" || (!sub.subscription_id && !!sub.order_id);
  return new Promise((resolve, reject) => {
    const checkout = new Razorpay({
      key: sub.key_id,
      ...(byOrder ? { order_id: sub.order_id, amount: sub.amount, currency: "INR" } : { subscription_id: sub.subscription_id }),
      name: sub.name,
      description: sub.description,
      prefill: sub.prefill,
      theme: { color: "#0E6B4F" },
      handler: (r: { razorpay_payment_id: string; razorpay_signature: string; razorpay_subscription_id?: string; razorpay_order_id?: string }) =>
        resolve({
          payment_id: r.razorpay_payment_id,
          signature: r.razorpay_signature,
          ...(byOrder ? { order_id: r.razorpay_order_id ?? sub.order_id } : { subscription_id: r.razorpay_subscription_id ?? sub.subscription_id }),
        }),
      modal: { ondismiss: () => resolve(null) },
    });
    checkout.on("payment.failed", () => reject(new Error("The payment didn't go through. Nothing was charged; try again.")));
    checkout.open();
  });
}

/** The phone's payment handoff, when the app sent the person here (see app/pay). */
export function appHandoff(orgId: string | null = null): string | null {
  try {
    const saved = JSON.parse(sessionStorage.getItem("fct_handoff") || "null") as { handoff_id?: string; org_id?: string | null } | null;
    return saved?.handoff_id && (saved.org_id ?? null) === orgId ? saved.handoff_id : null;
  } catch {
    return null;
  }
}

export function forgetHandoff() {
  try {
    sessionStorage.removeItem("fct_handoff");
  } catch {}
}
