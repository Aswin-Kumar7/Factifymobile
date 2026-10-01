// The price list, as the server sells it (app/orgs/plans.py; GET /v1/plans). Kept
// here too so the landing page renders without a round trip; the server is the one
// that charges, so a change there must be made here as well.

type PlanId = "free" | "plus" | "pro" | "team";

export type Plan = {
  id: PlanId;
  name: string;
  monthlyChecks: number;
  monthInr: number;
  yearInr: number;
  blurb: string;
  features: string[];
  popular?: boolean;
  team?: boolean;
  minSeats?: number;
};

export const EXTRA_CHECK_INR = 3;
export const API_CHECK_INR = 4;

export const PERSONAL: Plan[] = [
  {
    id: "free",
    name: "Free",
    monthlyChecks: 30,
    monthInr: 0,
    yearInr: 0,
    blurb: "Try Factify on the forwards you get.",
    features: ["Messages, links, pictures, PDFs, videos", "Website and Android app", "Every source shown", "Corrections ready to share"],
  },
  {
    id: "plus",
    name: "Plus",
    monthlyChecks: 120,
    monthInr: 299,
    yearInr: 2_990,
    blurb: "For anyone who checks forwards every day.",
    features: ["Everything in Free", "4× the checks of Free", `Extra usage at ₹${EXTRA_CHECK_INR} a check, if you want it`, "Pay by UPI or card"],
    popular: true,
  },
  {
    id: "pro",
    name: "Pro",
    monthlyChecks: 400,
    monthInr: 799,
    yearInr: 7_990,
    blurb: "For journalists, researchers and group admins.",
    features: ["Everything in Plus", "Over 13× the checks of Free", `Extra usage at ₹${EXTRA_CHECK_INR} a check, if you want it`, "Pay by UPI or card"],
  },
];

export const TEAM: Plan = {
  id: "team",
  name: "Team",
  monthlyChecks: 300,
  monthInr: 599,
  yearInr: 5_988,
  blurb: "For desks, NGOs and fact-check teams.",
  features: ["Everything in Pro", "One pool, with limits per member", "API keys and usage by person", `Extra usage at ₹${EXTRA_CHECK_INR} a check`],
  popular: true,
  team: true,
  minSeats: 3,
};

/** What a plan costs a month, billed monthly or yearly. */
export function perMonth(plan: Plan, yearly: boolean) {
  return yearly ? Math.round(plan.yearInr / 12) : plan.monthInr;
}

export const rupees = (value: number) => `₹${new Intl.NumberFormat("en-IN").format(value)}`;
