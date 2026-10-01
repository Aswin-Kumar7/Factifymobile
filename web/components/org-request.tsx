"use client";

// Asking for an organisation plan. Factify's admin reviews each request; when it is
// approved the organisation appears in the account switcher with the asker as owner.

import { useCallback, useEffect, useState } from "react";
import { useAccount } from "./account";
import { Badge, Button, Card, Field, Input, inputClass, Notice } from "./ui";
import { api } from "@/lib/api";
import { when } from "@/lib/format";

type Request = {
  id: string;
  org_name: string;
  status: "pending" | "approved" | "rejected" | "withdrawn";
  created_at: string;
  decided_at: string | null;
  decision_note: string | null;
  org_id: string | null;
};

const tone = { pending: "warn", approved: "acc", rejected: "bad", withdrawn: "neutral" } as const;
const word = { pending: "Waiting for review", approved: "Approved", rejected: "Not approved", withdrawn: "Withdrawn" };

export function OrgRequest() {
  const { me, refresh } = useAccount();
  const [requests, setRequests] = useState<Request[] | null>(null);
  const [form, setForm] = useState({ org_name: "", billing_email: me?.email ?? "", use_case: "", expected_checks: "", website: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const list = await api<Request[]>("/v1/org-requests", { account: "personal" }).catch(() => [] as Request[]);
    setRequests(list);
    // An approval since last time: the new organisation should be in the switcher.
    if (list.some((r) => r.status === "approved")) refresh().catch(() => undefined);
  }, [refresh]);
  useEffect(() => {
    load();
  }, [load]);

  const pending = requests?.find((r) => r.status === "pending");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/v1/org-requests", {
        method: "POST",
        json: {
          org_name: form.org_name.trim(),
          billing_email: form.billing_email.trim() || null,
          use_case: form.use_case.trim() || null,
          expected_checks: form.expected_checks ? Number(form.expected_checks) : null,
          website: form.website.trim() || null,
        },
        account: "personal",
      });
      await load();
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      {pending ? (
        <Card className="bg-hi">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-sm text-ink3">Your request</div>
              <div className="text-xl font-medium tracking-tight text-ink">{pending.org_name}</div>
              <div className="text-sm text-ink2">Sent {when(pending.created_at, true)}. We usually reply within a day.</div>
            </div>
            <div className="flex items-center gap-2">
              <Badge tone="warn">Waiting for review</Badge>
              <Button
                variant="ghost"
                size="sm"
                onClick={async () => {
                  await api(`/v1/org-requests/${pending.id}`, { method: "DELETE", account: "personal" });
                  load();
                }}
              >
                Withdraw
              </Button>
            </div>
          </div>
        </Card>
      ) : (
        <Card>
          <form onSubmit={submit} className="grid gap-4 md:grid-cols-2">
            <Field label="Organisation name">
              <Input required maxLength={80} value={form.org_name} onChange={(e) => setForm({ ...form, org_name: e.target.value })} placeholder="Acme News" />
            </Field>
            <Field label="Billing email">
              <Input type="email" value={form.billing_email} onChange={(e) => setForm({ ...form, billing_email: e.target.value })} />
            </Field>
            <Field label="Website (optional)">
              <Input value={form.website} onChange={(e) => setForm({ ...form, website: e.target.value })} placeholder="acmenews.in" />
            </Field>
            <Field label="Checks a month, roughly (optional)">
              <Input type="number" min={0} value={form.expected_checks} onChange={(e) => setForm({ ...form, expected_checks: e.target.value })} placeholder="2000" />
            </Field>
            <div className="md:col-span-2">
              <Field label="What will your team use Factify for?">
                <textarea
                  value={form.use_case}
                  onChange={(e) => setForm({ ...form, use_case: e.target.value })}
                  maxLength={1000}
                  rows={3}
                  placeholder="A newsroom desk checking forwards before publishing; an API for our CMS…"
                  className={inputClass}
                />
              </Field>
            </div>
            {error && (
              <div className="md:col-span-2">
                <Notice tone="error">{error}</Notice>
              </div>
            )}
            <div className="md:col-span-2">
              <Button type="submit" busy={busy}>
                Send request
              </Button>
            </div>
          </form>
        </Card>
      )}

      {requests && requests.filter((r) => r.status !== "pending").length > 0 && (
        <Card>
          <h3 className="mb-2 font-medium text-ink">Earlier requests</h3>
          <ul className="divide-y divide-line">
            {requests
              .filter((r) => r.status !== "pending")
              .map((r) => (
                <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5 text-sm">
                  <span className="text-ink">{r.org_name}</span>
                  <span className="flex items-center gap-2">
                    {r.decision_note && <span className="text-ink3">“{r.decision_note}”</span>}
                    <Badge tone={tone[r.status]}>{word[r.status]}</Badge>
                    {r.org_id && (
                      <a href={`/app/org/${r.org_id}`} className="font-medium text-acc-ink">
                        Open
                      </a>
                    )}
                  </span>
                </li>
              ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
