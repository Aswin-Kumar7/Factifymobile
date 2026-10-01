"use client";

// Settings: your profile, the theme, your data, and signing out - one column of
// sections, each with what it does on the left.

import { useState } from "react";
import { useAccount } from "@/components/account";
import { applyTheme, Mode, useTheme } from "@/components/theme";
import { Avatar, Button, Field, Input, Notice, PageTitle } from "@/components/ui";
import { api, authAction } from "@/lib/api";
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

const THEMES: [Mode, string, string][] = [
  ["dark", "Dark", "linear-gradient(135deg, #0a0d0b 62%, #5be4a8 62%)"],
  ["light", "Light", "linear-gradient(135deg, #f4f3ef 62%, #0e6b4f 62%)"],
  ["system", "Same as device", "linear-gradient(90deg, #0a0d0b 50%, #f4f3ef 50%)"],
];

export default function Settings() {
  const { me, refresh } = useAccount();
  const [mode] = useTheme();
  const [name, setName] = useState(me?.name ?? "");
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);
  const [cleared, setCleared] = useState(false);
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

      <Section title="Appearance" sub="Dark, light, or whatever your device uses.">
        <div role="radiogroup" aria-label="Theme" className="grid grid-cols-3 gap-3">
          {THEMES.map(([id, label, preview]) => (
            <button
              key={id}
              type="button"
              role="radio"
              aria-checked={mode === id}
              onClick={() => applyTheme(id)}
              className={`flex flex-col gap-2.5 rounded-[12px] border p-2.5 text-left text-[13px] text-ink transition-colors ${
                mode === id ? "border-acc-ink ring-3 ring-acc-ink/15" : "border-line2 hover:border-ink3"
              }`}
            >
              <span className="h-16 rounded-lg border border-line" style={{ background: preview }} />
              {label}
            </button>
          ))}
        </div>
      </Section>

      <Section title="Privacy & data" sub="Your history is kept in this browser only. Pictures and videos leave our servers after 24 hours.">
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
          <a href="mailto:aswin.aswin5640@gmail.com?subject=Delete%20my%20Factify%20account" className="inline-flex h-10 items-center rounded-[9px] border border-false/40 px-4 text-sm font-medium text-false hover:bg-false-soft">
            Delete account
          </a>
        </div>
        <p className="mt-2.5 text-xs text-ink3">Deleting is done by email from this address: we delete your account, credits and survey answers.</p>
      </Section>

      <Section title="Sign out" sub="Signs you out of this browser only.">
        <Button
          variant="outline"
          onClick={async () => {
            await authAction("logout").catch(() => undefined);
            try {
              localStorage.removeItem("fct_account");
            } catch {}
            window.location.href = "/";
          }}
        >
          Log out
        </Button>
      </Section>
    </div>
  );
}
