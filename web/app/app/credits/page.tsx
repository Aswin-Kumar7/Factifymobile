"use client";

import Link from "next/link";
import { useAccount } from "@/components/account";
import { Card, PageTitle, Stat } from "@/components/ui";
import { n, roleName } from "@/lib/format";

export default function Credits() {
  const { me, orgs } = useAccount();
  if (!me) return null;
  return (
    <>
      <PageTitle title="Credits" sub="Your personal credits, shared with the phone app." />
      <div className="grid gap-4 sm:grid-cols-3">
        <Stat label="Left" value={n(me.credits.balance)} sub="free credits" />
        <Stat label="Used" value={n(me.credits.used)} />
        <Stat label="Checks" value={n(me.credits.checks)} />
      </div>
      <Card className="mt-6">
        <h2 className="font-semibold text-ink">What a check costs</h2>
        <p className="mt-1 text-[15px] text-ink2">Text, a link, a picture or a PDF: 1 credit. A video: 3. A check that fails costs nothing.</p>
      </Card>
      {orgs.length > 0 && (
        <Card className="mt-4">
          <h2 className="font-semibold text-ink">Your organisations</h2>
          <ul className="mt-2 divide-y divide-line">
            {orgs.map((o) => (
              <li key={o.id} className="flex items-center justify-between gap-3 py-2.5">
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
      <Card className="mt-4">
        <h2 className="font-semibold text-ink">Need more?</h2>
        <p className="mt-1 text-[15px] text-ink2">
          Set up an organisation: buy credit packs for your team, give each person a limit, and use the API.
        </p>
        <Link href="/app/org/new" className="mt-3 inline-block rounded-xl bg-acc px-4 py-2.5 font-semibold text-on-acc">
          Create an organisation
        </Link>
      </Card>
    </>
  );
}
