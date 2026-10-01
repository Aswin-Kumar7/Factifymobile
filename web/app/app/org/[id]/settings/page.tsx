"use client";

import { useRouter } from "next/navigation";
import { use, useCallback, useEffect, useState } from "react";
import { useAccount } from "@/components/account";
import { Badge, Button, Card, CopyButton, Field, Input, Notice, PageTitle, Select, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { useOrg } from "@/lib/use-org";

type Domain = {
  domain: string;
  verified_at: string | null;
  auto_join: boolean;
  default_role: "member" | "developer";
  record_name: string;
  record_value: string;
};

export default function Settings({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { org, error, reload } = useOrg(id);
  const { refresh, choose } = useAccount();
  const router = useRouter();
  const [form, setForm] = useState({ name: "", billing_email: "", gst_number: "", limit: "", shared: false });
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: "success" | "error"; text: string } | null>(null);

  useEffect(() => {
    if (org)
      setForm({
        name: org.name,
        billing_email: org.billing_email ?? "",
        gst_number: org.gst_number ?? "",
        limit: org.monthly_spend_limit != null ? String(org.monthly_spend_limit) : "",
        shared: org.shared_history,
      });
  }, [org]);

  if (error) return <Notice tone="error">{error}</Notice>;
  if (!org) return <Spinner />;
  if (org.my_role !== "owner") return <Notice tone="info">Only owners can change settings.</Notice>;

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      await api(`/v1/orgs/${id}`, {
        method: "PATCH",
        json: {
          name: form.name.trim(),
          billing_email: form.billing_email.trim() || null,
          gst_number: form.gst_number.trim() || null,
          shared_history: form.shared,
          ...(form.limit === "" ? { clear_spend_limit: true } : { monthly_spend_limit: Number(form.limit) }),
        },
        account: "personal",
      });
      await Promise.all([reload(), refresh()]);
      setMessage({ tone: "success", text: "Saved." });
    } catch (failure) {
      setMessage({ tone: "error", text: (failure as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageTitle eyebrow={org.name} title="Settings" />
      <Card>
        <form onSubmit={save} className="grid gap-4 md:grid-cols-2">
          <Field label="Organisation name">
            <Input required maxLength={80} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </Field>
          <Field label="Billing email">
            <Input type="email" value={form.billing_email} onChange={(e) => setForm({ ...form, billing_email: e.target.value })} />
          </Field>
          <Field label="GST number (optional)" hint="Printed on invoices.">
            <Input maxLength={20} value={form.gst_number} onChange={(e) => setForm({ ...form, gst_number: e.target.value })} />
          </Field>
          <Field label="Monthly spending limit" hint="Credits a month for the whole organisation. Empty: no limit.">
            <Input type="number" min={0} value={form.limit} onChange={(e) => setForm({ ...form, limit: e.target.value })} />
          </Field>
          <label className="flex cursor-pointer gap-3 rounded-xl border border-line p-3 md:col-span-2">
            <input
              type="checkbox"
              checked={form.shared}
              onChange={(e) => setForm({ ...form, shared: e.target.checked })}
              className="mt-1 h-4 w-4 accent-[var(--acc)]"
            />
            <span>
              <span className="block font-semibold text-ink">Keep a shared history of checks</span>
              <span className="block text-sm text-ink2">
                Members see the organisation&apos;s checks: what was checked, the verdict, and who or which key checked it.
                Off by default; personal checks are never included.
              </span>
            </span>
          </label>
          {message && (
            <div className="md:col-span-2">
              <Notice tone={message.tone}>{message.text}</Notice>
            </div>
          )}
          <div className="md:col-span-2">
            <Button type="submit" busy={busy}>
              Save settings
            </Button>
          </div>
        </form>
      </Card>

      <Domains orgId={id} />

      <Card className="mt-6 border-false/40">
        <h2 className="font-semibold text-false">Close this organisation</h2>
        <p className="mt-1 text-sm text-ink2">All its API keys stop at once, and members can no longer check with its credits.</p>
        <Button
          variant="danger"
          className="mt-3"
          onClick={async () => {
            if (prompt(`Type the organisation's name to close it: ${org.name}`) !== org.name) return;
            try {
              await api(`/v1/orgs/${id}`, { method: "DELETE", account: "personal" });
            } catch (failure) {
              setMessage({ tone: "error", text: (failure as Error).message });
              return;
            }
            choose("personal");
            await refresh();
            router.push("/app/check");
          }}
        >
          Close organisation
        </Button>
      </Card>
    </>
  );
}

function Domains({ orgId }: { orgId: string }) {
  const [domains, setDomains] = useState<Domain[] | null>(null);
  const [adding, setAdding] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState<string | null>(null);

  const load = useCallback(async () => {
    setDomains(await api<Domain[]>(`/v1/orgs/${orgId}/domains`, { account: "personal" }).catch(() => []));
  }, [orgId]);
  useEffect(() => {
    load();
  }, [load]);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api(`/v1/orgs/${orgId}/domains`, { method: "POST", json: { domain: adding.trim() }, account: "personal" });
      setAdding("");
      load();
    } catch (failure) {
      setError((failure as Error).message);
    }
  }

  return (
    <Card className="mt-6">
      <h2 className="font-semibold text-ink">Verified domains</h2>
      <p className="mt-1 text-sm text-ink2">
        Prove you own your email domain, then people who sign in with an address there can join automatically.
      </p>
      <form onSubmit={add} className="mt-4 flex flex-col gap-2 sm:flex-row">
        <Input value={adding} onChange={(e) => setAdding(e.target.value)} placeholder="example.com" className="sm:max-w-xs" />
        <Button type="submit" variant="outline">
          Add domain
        </Button>
      </form>
      {error && (
        <div className="mt-3">
          <Notice tone="error">{error}</Notice>
        </div>
      )}
      <div className="mt-4 space-y-3">
        {domains?.map((d) => (
          <div key={d.domain} className="rounded-xl border border-line p-3 sm:p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-ink">{d.domain}</span>
                <Badge tone={d.verified_at ? "acc" : "warn"}>{d.verified_at ? "Verified" : "Not verified"}</Badge>
              </div>
              <Button
                variant="ghost"
                size="sm"
                className="text-false"
                onClick={async () => {
                  setError(null);
                  await api(`/v1/orgs/${orgId}/domains/${d.domain}`, { method: "DELETE", account: "personal" }).catch((failure: Error) => setError(failure.message));
                  load();
                }}
              >
                Remove
              </Button>
            </div>
            {!d.verified_at ? (
              <div className="mt-3 space-y-2 text-sm text-ink2">
                <p>Add this TXT record in your domain&apos;s DNS, then check it:</p>
                <div className="grid gap-2 sm:grid-cols-[auto_1fr_auto] sm:items-center">
                  <span className="text-xs font-semibold text-ink3">Name</span>
                  <code className="rounded-lg bg-sf2 px-2 py-1 font-mono text-xs break-all">{d.record_name}</code>
                  <CopyButton text={d.record_name} />
                  <span className="text-xs font-semibold text-ink3">Value</span>
                  <code className="rounded-lg bg-sf2 px-2 py-1 font-mono text-xs break-all">{d.record_value}</code>
                  <CopyButton text={d.record_value} />
                </div>
                <Button
                  size="sm"
                  busy={checking === d.domain}
                  onClick={async () => {
                    setChecking(d.domain);
                    setError(null);
                    try {
                      const r = await api<{ verified: boolean }>(`/v1/orgs/${orgId}/domains/${d.domain}/verify`, {
                        method: "POST",
                        account: "personal",
                      });
                      if (!r.verified) setError("The record isn't there yet. DNS changes can take up to an hour.");
                      load();
                    } catch (failure) {
                      setError((failure as Error).message);
                    } finally {
                      setChecking(null);
                    }
                  }}
                >
                  Check DNS
                </Button>
              </div>
            ) : (
              <div className="mt-3 flex flex-col gap-3 text-sm sm:flex-row sm:items-center">
                <label className="flex items-center gap-2 text-ink">
                  <input
                    type="checkbox"
                    checked={d.auto_join}
                    className="h-4 w-4 accent-[var(--acc)]"
                    onChange={async (e) => {
                      await api(`/v1/orgs/${orgId}/domains/${d.domain}`, {
                        method: "PATCH",
                        json: { auto_join: e.target.checked },
                        account: "personal",
                      }).catch((failure: Error) => setError(failure.message));
                      load();
                    }}
                  />
                  Anyone @{d.domain} joins automatically as
                </label>
                <Select
                  value={d.default_role}
                  className="w-auto"
                  onChange={async (e) => {
                    await api(`/v1/orgs/${orgId}/domains/${d.domain}`, {
                      method: "PATCH",
                      json: { default_role: e.target.value },
                      account: "personal",
                    }).catch((failure: Error) => setError(failure.message));
                    load();
                  }}
                >
                  <option value="member">Member</option>
                  <option value="developer">Developer</option>
                </Select>
              </div>
            )}
          </div>
        ))}
      </div>
    </Card>
  );
}
