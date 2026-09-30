"use client";

import { useState } from "react";
import { useAccount } from "@/components/account";
import { Button, Card, Field, Input, Notice, PageTitle } from "@/components/ui";
import { api, authAction } from "@/lib/api";
import { when } from "@/lib/format";

export default function Profile() {
  const { me, refresh } = useAccount();
  const [name, setName] = useState(me?.name ?? "");
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);
  if (!me) return null;

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setSaved(null);
    try {
      await api("/v1/me", { method: "PATCH", json: { name: name.trim() }, account: "personal" });
      await refresh();
      setSaved("Saved.");
    } catch (failure) {
      setSaved((failure as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageTitle title="Profile" />
      <Card>
        <form onSubmit={save} className="max-w-md space-y-4">
          <Field label="Name">
            <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={60} required />
          </Field>
          <Field label="Email">
            <Input value={me.email} disabled />
          </Field>
          <div className="text-sm text-ink3">Joined {when(me.joined_at)}</div>
          {saved && <Notice tone={saved === "Saved." ? "success" : "error"}>{saved}</Notice>}
          <Button type="submit" busy={busy}>
            Save
          </Button>
        </form>
      </Card>
      <Card className="mt-4">
        <h2 className="font-semibold text-ink">Sign out</h2>
        <p className="mt-1 text-sm text-ink2">Signs you out of this browser.</p>
        <Button
          variant="outline"
          className="mt-3"
          onClick={async () => {
            await authAction("logout").catch(() => undefined);
            window.location.href = "/";
          }}
        >
          Sign out
        </Button>
      </Card>
      <Card className="mt-4">
        <h2 className="font-semibold text-ink">Delete your account</h2>
        <p className="mt-1 text-sm text-ink2">
          Email <a className="text-acc-ink underline" href="mailto:aswin.aswin5640@gmail.com">aswin.aswin5640@gmail.com</a> from
          this address and we&apos;ll delete your account, credits and survey answers.
        </p>
      </Card>
    </>
  );
}
