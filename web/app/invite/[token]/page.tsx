"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { api, ApiFailure } from "@/lib/api";
import { roleName } from "@/lib/format";
import { Button, Notice, Seal, Spinner } from "@/components/ui";

type Invite = { org_name: string; email: string; role: keyof typeof roleName; expires_at: string; accepted: boolean };

export default function InvitePage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params);
  const [invite, setInvite] = useState<Invite | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [signedIn, setSignedIn] = useState<string | null | undefined>(undefined);

  useEffect(() => {
    api<Invite>(`/v1/invites/${token}`)
      .then(setInvite)
      .catch((e: Error) => setError(e.message));
    fetch("/api/f/v1/me", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((me) => setSignedIn(me?.email ?? null))
      .catch(() => setSignedIn(null));
  }, [token]);

  async function accept() {
    setBusy(true);
    setError(null);
    try {
      const joined = await api<{ org_id: string }>(`/v1/invites/${token}/accept`, { method: "POST", account: "personal" });
      window.location.href = `/app/org/${joined.org_id}`;
    } catch (e) {
      setError(e instanceof ApiFailure ? e.message : "That didn't work.");
      setBusy(false);
    }
  }

  const here = `/invite/${token}`;
  return (
    <main className="flex min-h-dvh items-center justify-center px-4 py-10">
      <div className="w-full max-w-md rounded-[14px] border border-line bg-sf p-6 sm:p-8">
        <Seal size={52} />
        {!invite && !error && (
          <p className="mt-6 flex items-center gap-2 text-ink2">
            <Spinner /> Opening the invitation…
          </p>
        )}
        {invite && (
          <>
            <h1 className="mt-6 text-3xl font-medium tracking-tight text-ink">Join {invite.org_name}</h1>
            <p className="mt-2 text-[15px] text-ink2">
              You&apos;re invited as a <strong>{roleName[invite.role]}</strong>, as {invite.email}. Checks you make for{" "}
              {invite.org_name} are paid from its credits.
            </p>
            {invite.accepted ? (
              <Notice tone="info">This invitation has already been used.</Notice>
            ) : signedIn === undefined ? null : signedIn ? (
              <div className="mt-6 space-y-3">
                {signedIn.toLowerCase() !== invite.email && (
                  <Notice tone="warning">
                    You&apos;re signed in as {signedIn}. This invitation is for {invite.email}; sign in with that email to
                    accept it.
                  </Notice>
                )}
                <Button onClick={accept} busy={busy} className="w-full" size="lg">
                  Join {invite.org_name}
                </Button>
              </div>
            ) : (
              <div className="mt-6 grid gap-2">
                <Link href={`/signup?next=${encodeURIComponent(here)}`} className="rounded-[9px] bg-acc py-3 text-center font-semibold text-on-acc">
                  Create an account to join
                </Link>
                <Link href={`/signin?next=${encodeURIComponent(here)}`} className="rounded-xl border border-line py-3 text-center font-semibold text-ink">
                  I have an account
                </Link>
              </div>
            )}
          </>
        )}
        {error && (
          <div className="mt-6">
            <Notice tone="error">{error}</Notice>
          </div>
        )}
      </div>
    </main>
  );
}
