"use client";

import Link from "next/link";
import { OrgRequest } from "@/components/org-request";
import { PageTitle } from "@/components/ui";
import { TEAM, rupees } from "@/lib/plans";

const STEPS = [
  "The Factify team reviews your request, usually within a day.",
  "Once approved, your organisation appears in the workspace switcher, with you as its owner.",
  "Choose the Team plan (or pay per check through the API), invite people, and create API keys.",
  "Your personal plan and history stay yours.",
];

export default function RequestOrg() {
  return (
    <div className="flex flex-col gap-5">
      <PageTitle title="Create an organisation" sub="One shared pool of checks for your desk, NGO or company - with members, roles, API keys and usage by person." />
      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,.65fr)]">
        <OrgRequest />
        <aside className="flex flex-col gap-3.5 rounded-[14px] border border-line bg-sf p-5.5 shadow-card">
          <h2 className="text-[15px] font-medium text-ink">What happens next</h2>
          <ol className="flex flex-col gap-3">
            {STEPS.map((s, i) => (
              <li key={s} className="grid grid-cols-[24px_minmax(0,1fr)] gap-2.5 text-sm leading-relaxed text-ink2">
                <span className="flex h-6 w-6 items-center justify-center rounded-full border border-line2 font-mono text-[11px] text-ink">{i + 1}</span>
                {s}
              </li>
            ))}
          </ol>
          <div className="h-px bg-line" />
          <p className="text-[13px] text-ink3">
            Team plan · {rupees(TEAM.monthInr)} per member a month, from {TEAM.minSeats} members, {TEAM.monthlyChecks} checks each.{" "}
            <Link href="/#pricing" className="text-acc-ink">
              See plans
            </Link>
          </p>
        </aside>
      </div>
    </div>
  );
}
