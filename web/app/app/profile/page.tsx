"use client";

// Settings: your profile, your data, and signing out - one column of sections,
// each with what it does on the left.

import { useState } from "react";
import { useAccount } from "@/components/account";
import { Avatar, Button, Field, Input, Notice, PageTitle } from "@/components/ui";
import { api, ApiFailure, authAction } from "@/lib/api";
import { when } from "@/lib/format";
import { clearHistory } from "@/lib/history";

function Section({ title, sub, children, first }: { title: string; sub: string; children: React.ReactNode; first?: boolean }) {
  return (
    <section className={`grid gap-4 py-6.5 md:grid-cols-[minmax(0,.75fr)_minmax(0,1.25fr)] md:gap-8 ${first ? "pt-0" : "border-t border-line"}`}>
      <div>
        <h2 className="text-base font-medium text-ink">{title}</h2>
        <p className="mt-1 text-sm leading-relaxed text-ink3">{sub}</p>
      </div>
      <div>{children}</div>
    </section>
  );
}

export default function Settings() {
  const { me, refresh } = useAccount();
  const [name, setName] = useState(me?.name ?? "");
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);
  const [cleared, setCleared] = useState(false);
  const [deleting, setDeleting] = useState<"ask" | "busy" | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  if (!me) return null;
  const shownName = me.name || me.email.split("@")[0];

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

  async function signOut() {
    await authAction("logout").catch(() => undefined);
    try {
      localStorage.removeItem("fct_account");
    } catch {}
    window.location.href = "/";
  }

  async function deleteAccount() {
    setDeleting("busy");
    setDeleteError(null);
    try {
      await api("/v1/me", { method: "DELETE", account: "personal" });
      clearHistory();
      await signOut();
    } catch (failure) {
      setDeleting("ask");
      setDeleteError(failure instanceof ApiFailure ? failure.message : "That didn't work. Try again.");
    }
  }

  return (
    <div className="mx-auto max-w-[860px]">
      <PageTitle title="Settings" />

      <Section first title="Profile" sub="How you appear in Factify and in a team's shared history.">
        <form onSubmit={save} className="flex flex-col gap-4">
          <div className="flex items-center gap-3.5">
            <Avatar name={shownName} size={52} />
            <span>
              <span className="block text-[15px] font-medium text-ink">{shownName}</span>
              <span className="block text-[13px] text-acc-ink">{me.plan_usage?.name ?? "Free"} plan</span>
            </span>
          </div>
          <Field label="Full name">
            <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={60} required />
          </Field>
          <Field label="Email" hint={`Joined ${when(me.joined_at)}`}>
            <Input value={me.email} disabled />
          </Field>
          {saved && <Notice tone={saved === "Saved." ? "success" : "error"}>{saved}</Notice>}
          <div>
            <Button type="submit" busy={busy}>
              Save
            </Button>
          </div>
        </form>
      </Section>

      <Section title="Privacy & data" sub="Your list of past checks is kept in this browser only. Pictures, videos and PDFs you upload are never stored; we keep only a fingerprint of each picture, to recognise it if it's sent again.">
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            onClick={() => {
              if (confirm("Clear your history in this browser?")) {
                clearHistory();
                setCleared(true);
              }
            }}
          >
            {cleared ? "History cleared" : "Clear history on this device"}
          </Button>
          {deleting === null && (
            <button
              type="button"
              onClick={() => setDeleting("ask")}
              className="inline-flex h-10 items-center rounded-[9px] border border-false/40 px-4 text-sm font-medium text-false transition-colors hover:bg-false-soft"
            >
              Delete account
            </button>
          )}
        </div>
        {deleting !== null ? (
          <div className="mt-4 rounded-[12px] border border-false/40 bg-false-soft p-4">
            <p className="text-sm font-medium text-ink">Delete your account for good?</p>
            <p className="mt-1 text-[13px] leading-relaxed text-ink2">
              Your sign-in, credits, plan, payments and survey answers are deleted at once and can&apos;t be brought back. A plan you paid for stops with it.
            </p>
            {deleteError && (
              <div className="mt-3">
                <Notice tone="error">{deleteError}</Notice>
              </div>
            )}
            <div className="mt-3.5 flex flex-wrap gap-2">
              <Button variant="danger" busy={deleting === "busy"} onClick={deleteAccount}>
                Delete for good
              </Button>
              <Button variant="outline" onClick={() => { setDeleting(null); setDeleteError(null); }} disabled={deleting === "busy"}>
                Keep my account
              </Button>
            </div>
          </div>
        ) : (
          <p className="mt-2.5 text-xs text-ink3">Deleting removes your account, credits, plan and survey answers straight away.</p>
        )}
      </Section>

      <Section title="Sign out" sub="Signs you out of this browser only.">
        <Button variant="outline" onClick={signOut}>
          Log out
        </Button>
      </Section>
    </div>
  );
}
