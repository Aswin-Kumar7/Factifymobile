"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useAccount } from "@/components/account";
import { Button, Card, Field, Input, Notice, PageTitle } from "@/components/ui";
import { api, Org } from "@/lib/api";

export default function NewOrg() {
  const { me, refresh, choose } = useAccount();
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState(me?.email ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const org = await api<Org>("/v1/orgs", {
        method: "POST",
        json: { name: name.trim(), billing_email: email.trim() || null },
        account: "personal",
      });
      await refresh();
      choose(org.id);
      router.push(`/app/org/${org.id}`);
    } catch (failure) {
      setError((failure as Error).message);
      setBusy(false);
    }
  }

  return (
    <>
      <PageTitle title="Create an organisation" sub="One credit pool for your team, with limits per person and API keys." />
      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <Card>
          <form onSubmit={create} className="space-y-4">
            <Field label="Organisation name">
              <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} required placeholder="Acme News" />
            </Field>
            <Field label="Billing email" hint="Invoices and credit alerts go here.">
              <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
            </Field>
            {error && <Notice tone="error">{error}</Notice>}
            <Button type="submit" busy={busy} size="lg">
              Create organisation
            </Button>
          </form>
        </Card>
        <Card className="bg-sf2">
          <h2 className="font-semibold text-ink">What you get</h2>
          <ul className="mt-2 space-y-2 text-sm text-ink2">
            <li>You become its owner. You can add more owners later.</li>
            <li>Buy credit packs; every member&apos;s checks draw from the pool.</li>
            <li>Invite people as members or developers, each with a monthly limit.</li>
            <li>Developers and owners create API keys.</li>
            <li>Your 100 personal free credits stay yours.</li>
          </ul>
        </Card>
      </div>
    </>
  );
}
