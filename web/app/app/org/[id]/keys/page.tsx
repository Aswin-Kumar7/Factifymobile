"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import { Badge, Button, Card, CopyButton, Empty, Field, Input, Modal, Notice, PageTitle, Spinner, Table } from "@/components/ui";
import { api, ApiKey } from "@/lib/api";
import { ago, n, when } from "@/lib/format";
import { useOrg } from "@/lib/use-org";

function state(k: ApiKey): [string, "acc" | "warn" | "bad" | "neutral"] {
  if (k.revoked_at && new Date(k.revoked_at) <= new Date()) return ["Revoked", "bad"];
  if (k.replaced_by) return [`Rotated · works until ${when(k.revoked_at, true)}`, "warn"];
  if (k.expires_at && new Date(k.expires_at) <= new Date()) return ["Expired", "bad"];
  return ["Active", "acc"];
}

export default function Keys({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { org } = useOrg(id);
  const [keys, setKeys] = useState<ApiKey[] | null>(null);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<ApiKey | null>(null);
  const [shown, setShown] = useState<ApiKey | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setKeys(await api<ApiKey[]>(`/v1/orgs/${id}/keys`, { account: "personal" }));
  }, [id]);
  useEffect(() => {
    if (org) load().catch((e: Error) => setError(e.message));
  }, [org, load]);

  if (org && org.my_role === "member") {
    return (
      <>
        <PageTitle title="API keys" />
        <Notice tone="info">Only owners and developers can use API keys. Ask an owner of {org.name} to make you a developer.</Notice>
      </>
    );
  }
  if (!org || (!keys && !error)) return <Spinner />;

  async function rotate(k: ApiKey) {
    if (!confirm(`Rotate “${k.name}”? You'll get a new key; the old one keeps working for 24 hours.`)) return;
    try {
      setShown(await api<ApiKey>(`/v1/orgs/${id}/keys/${k.id}/rotate`, { method: "POST", account: "personal" }));
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function revoke(k: ApiKey) {
    if (!confirm(`Revoke “${k.name}” now? Anything using it will stop working.`)) return;
    try {
      await api(`/v1/orgs/${id}/keys/${k.id}`, { method: "DELETE", account: "personal" });
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <>
      <PageTitle
        eyebrow={org.name}
        title="API keys"
        sub={
          <>
            {org.my_role === "owner" ? "Every key in the organisation." : "Your keys."} Checks made with a key are paid from{" "}
            {org.name}&apos;s credits. <Link href="/docs" className="font-semibold text-acc-ink">API docs</Link>
          </>
        }
        action={<Button onClick={() => setCreating(true)}>Create a key</Button>}
      />
      {error && (
        <div className="mb-4">
          <Notice tone="error">{error}</Notice>
        </div>
      )}
      {keys && keys.length === 0 ? (
        <Empty title="No keys yet">Create a key for each tool or integration, so you can see and limit what each one spends.</Empty>
      ) : (
        <Card className="p-0 sm:p-0">
          <Table head={["Name", "Key", "Status", "This month", "Last used", ""]}>
            {keys?.map((k) => {
              const [label, tone] = state(k);
              const live = label === "Active";
              return (
                <tr key={k.id} className={live ? "" : "opacity-70"}>
                  <td>
                    <div className="font-medium text-ink">{k.name}</div>
                    <div className="max-w-[220px] truncate text-xs text-ink3">{k.note || k.created_by_email}</div>
                  </td>
                  <td className="font-mono text-xs whitespace-nowrap text-ink2">{k.prefix}…</td>
                  <td>
                    <Badge tone={tone}>{label}</Badge>
                  </td>
                  <td className="whitespace-nowrap text-ink2">
                    {n(k.month_spend)}
                    {k.monthly_limit != null && ` / ${n(k.monthly_limit)}`}
                  </td>
                  <td className="whitespace-nowrap text-ink2">{ago(k.last_used_at)}</td>
                  <td className="text-right whitespace-nowrap">
                    {live && (
                      <>
                        <Button variant="ghost" size="sm" onClick={() => setEditing(k)}>
                          Edit
                        </Button>
                        <Button variant="ghost" size="sm" onClick={() => rotate(k)}>
                          Rotate
                        </Button>
                        <Button variant="ghost" size="sm" className="text-false" onClick={() => revoke(k)}>
                          Revoke
                        </Button>
                      </>
                    )}
                  </td>
                </tr>
              );
            })}
          </Table>
        </Card>
      )}

      <p className="mt-4 text-sm text-ink3">
        Keys are shown once, when they&apos;re created. We keep only a fingerprint, so a lost key can&apos;t be recovered:
        rotate it instead.
      </p>

      <KeyForm open={creating} orgId={id} onClose={() => setCreating(false)} onCreated={(k) => { setShown(k); load(); }} />
      {editing && <KeyForm open orgId={id} existing={editing} onClose={() => setEditing(null)} onCreated={() => load()} />}

      <Modal open={!!shown} title="Your new API key" onClose={() => setShown(null)}>
        {shown?.key && (
          <div className="space-y-4">
            <Notice tone="warning">Copy it now. For your security it won&apos;t be shown again.</Notice>
            <div className="rounded-xl bg-sf2 p-3 font-mono text-sm break-all text-ink select-all">{shown.key}</div>
            <div className="flex gap-2">
              <CopyButton text={shown.key} label="Copy key" />
              <Button variant="ghost" size="sm" onClick={() => setShown(null)}>
                I&apos;ve saved it
              </Button>
            </div>
            <pre className="overflow-x-auto rounded-xl bg-[#1c1b18] p-3 font-mono text-xs text-[#f1efe8]">{`curl ${typeof window !== "undefined" ? window.location.origin : ""}/v1/verify \\
  -H "Authorization: Bearer ${shown.key}" \\
  -H "Content-Type: application/json" \\
  -d '{"text": "RBI keeps repo rate unchanged"}'`}</pre>
          </div>
        )}
      </Modal>
    </>
  );
}

function KeyForm({
  open,
  orgId,
  existing,
  onClose,
  onCreated,
}: {
  open: boolean;
  orgId: string;
  existing?: ApiKey;
  onClose: () => void;
  onCreated: (k: ApiKey) => void;
}) {
  const [name, setName] = useState(existing?.name ?? "");
  const [note, setNote] = useState(existing?.note ?? "");
  const [limit, setLimit] = useState(existing?.monthly_limit != null ? String(existing.monthly_limit) : "");
  const [expires, setExpires] = useState("");
  const [ips, setIps] = useState((existing?.ip_allowlist ?? []).join(", "));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const ipList = ips.split(/[\s,]+/).filter(Boolean);
    try {
      if (existing) {
        await api(`/v1/orgs/${orgId}/keys/${existing.id}`, {
          method: "PATCH",
          json: {
            name: name.trim(),
            note: note.trim() || null,
            ip_allowlist: ipList,
            ...(limit === "" ? { clear_limit: true } : { monthly_limit: Number(limit) }),
          },
          account: "personal",
        });
        onCreated(existing);
      } else {
        const key = await api<ApiKey>(`/v1/orgs/${orgId}/keys`, {
          method: "POST",
          json: {
            name: name.trim(),
            note: note.trim() || null,
            monthly_limit: limit ? Number(limit) : null,
            expires_days: expires ? Number(expires) : null,
            ip_allowlist: ipList,
          },
          account: "personal",
        });
        setName("");
        setNote("");
        setLimit("");
        setExpires("");
        setIps("");
        onCreated(key);
      }
      onClose();
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open={open} title={existing ? `Edit “${existing.name}”` : "Create an API key"} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <Field label="Name">
          <Input required maxLength={60} value={name} onChange={(e) => setName(e.target.value)} placeholder="Newsroom CMS" />
        </Field>
        <Field label="Where it's used (optional)">
          <Input maxLength={200} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Server env var on cms-prod" />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Monthly credit limit" hint="Empty: no limit">
            <Input type="number" min={0} value={limit} onChange={(e) => setLimit(e.target.value)} />
          </Field>
          {!existing && (
            <Field label="Expires after (days)" hint="Empty: never">
              <Input type="number" min={1} max={730} value={expires} onChange={(e) => setExpires(e.target.value)} />
            </Field>
          )}
        </div>
        <Field label="Allowed IP addresses (optional)" hint="Comma-separated. Empty: any address.">
          <Input value={ips} onChange={(e) => setIps(e.target.value)} placeholder="203.0.113.10, 203.0.113.11" />
        </Field>
        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" busy={busy} className="w-full">
          {existing ? "Save" : "Create key"}
        </Button>
      </form>
    </Modal>
  );
}
