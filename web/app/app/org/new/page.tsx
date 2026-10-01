"use client";

import { OrgRequest } from "@/components/org-request";
import { Card, PageTitle } from "@/components/ui";

export default function RequestOrg() {
  return (
    <>
      <PageTitle
        eyebrow="Organisation plan"
        title="Request an organisation plan"
        sub="One credit pool for your team, limits per person, and API keys. Tell us a little about your team; we review every request."
      />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <OrgRequest />
        <Card className="h-fit bg-sf2">
          <h2 className="font-semibold text-ink">What happens next</h2>
          <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm text-ink2">
            <li>The Factify team reviews your request, usually within a day.</li>
            <li>Once approved, your organisation appears in the account switcher, with you as its owner.</li>
            <li>Buy credits for the team, invite people, and create API keys.</li>
            <li>Your personal free credits stay yours.</li>
          </ol>
        </Card>
      </div>
    </>
  );
}
