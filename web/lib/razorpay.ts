"use client";

// Razorpay Checkout for a subscription: load its script once, open it on the
// subscription the server made, and resolve with Razorpay's signed result (or null
// when the person closes it). The server checks the signature; this only carries it.

export type Subscription = {
  subscription_id: string;
  key_id: string;
  name: string;
  description: string;
  prefill: { email: string };
  test_mode: boolean;
};

export type SubscriptionResult = {
  razorpay_payment_id: string;
  razorpay_subscription_id: string;
  razorpay_signature: string;
};

type Checkout = new (options: Record<string, unknown>) => { open: () => void; on: (e: string, f: (r: unknown) => void) => void };

let loading: Promise<void> | null = null;

function load(): Promise<void> {
  const w = window as unknown as { Razorpay?: Checkout };
  if (w.Razorpay) return Promise.resolve();
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

export async function payForSubscription(sub: Subscription): Promise<SubscriptionResult | null> {
  await load();
  const Razorpay = (window as unknown as { Razorpay: Checkout }).Razorpay;
  return new Promise((resolve, reject) => {
    const checkout = new Razorpay({
      key: sub.key_id,
      subscription_id: sub.subscription_id,
      name: sub.name,
      description: sub.description,
      prefill: sub.prefill,
      theme: { color: "#0E6B4F" },
      handler: (r: SubscriptionResult) => resolve(r),
      modal: { ondismiss: () => resolve(null) },
    });
    checkout.on("payment.failed", () => reject(new Error("The payment didn't go through. Nothing was charged; try again.")));
    checkout.open();
  });
}
