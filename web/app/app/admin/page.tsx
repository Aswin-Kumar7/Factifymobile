"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useAccount } from "@/components/account";
import { Badge, Bars, Button, Card, Field, Input, Modal, Notice, PageTitle, Spinner, Stat, Table } from "@/components/ui";
import { api } from "@/lib/api";
import { ago, inr, n, when } from "@/lib/format";

type Stats = {
  totals: Record<string, number>;
  by_day: { day: string; checks: number; videos: number }[];
  providers: { provider: string; calls: number; daily_cap: number }[];
  survey: { survey_state: string; role: string | null; n: number }[];
};
type AdminOrg = { id: string; name: string; status: string; created_at: string; billing_email: string | null; balance: number; members: number; active_keys: number };
type AdminUser = {
  id: string;
  email: string;
  name: string | null;
  created_at: string;
  last_seen_at: string;
  is_staff: boolean;
  disabled: boolean;
  survey_state: string;
  balance: number;
  orgs: string | null;
};
type AdminKey = { id: string; org_id: string; org_name: string; name: string; prefix: string; created_at: string; last_used_at: string | null; revoked_at: string | null; created_by_email: string | null };
type AuditRow = { at: string; action: string; target: string | null; detail: Record<string, unknown>; actor_email: string | null };

const tabs = ["Overview", "Organisations", "People", "API keys", "Audit"] as const;
const roleWords: Record<string, string> = {
  journalist: "Journalists",
  student: "Students",
  teacher: "Teachers",
  family: "Checking for family",
  curious: "Curious",
};

export default function Admin() {
  const { me } = useAccount();
  const [tab, setTab] = useState<(typeof tabs)[number]>("Overview");
  if (!me?.is_staff) return <Notice tone="info">This page is for the Factify team.</Notice>;
  return (
    <>
      <PageTitle title="Admin" sub="Factify's own view: every organisation, person and key." />
      <div role="tablist" className="-mx-4 mb-6 flex gap-1 overflow-x-auto px-4 sm:mx-0 sm:px-0">
        {tabs.map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            onClick={() => setTab(t)}
            className={`shrink-0 rounded-xl px-4 py-2 text-sm font-semibold ${tab === t ? "bg-acc-soft text-acc-ink" : "text-ink2 hover:bg-sf2"}`}
          >
            {t}
          </button>
        ))}
      </div>
      {tab === "Overview" && <Overview />}
      {tab === "Organisations" && <Orgs />}
      {tab === "People" && <People />}
      {tab === "API keys" && <Keys />}
      {tab === "Audit" && <Audit />}
    </>
  );
}

function Overview() {
  const [stats, setStats] = useState<Stats | null>(null);
  useEffect(() => {
    api<Stats>("/v1/admin/stats", { account: "personal" }).then(setStats).catch(() => undefined);
  }, []);
  if (!stats) return <Spinner />;
  const t = stats.totals;
  const answered = stats.survey.filter((s) => s.survey_state === "answered");
  const map = new Map(stats.by_day.map((d) => [d.day, Number(d.checks)]));
  const series = Array.from({ length: 30 }, (_, i) => {
    const d = new Date(Date.now() - (29 - i) * 86400000).toISOString().slice(0, 10);
    return { label: d.slice(5), value: map.get(d) ?? 0 };
  });
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <Stat label="People" value={n(t.users)} sub={`${n(t.users_7d)} new this week`} />
        <Stat label="Organisations" value={n(t.orgs)} sub={`${n(t.active_keys)} active keys`} />
        <Stat label="Checks, 24 h" value={n(t.checks_24h)} sub={`${n(t.checks_30d)} in 30 days`} />
        <Stat label="Revenue" value={inr((t.revenue_paise ?? 0) / 100)} sub={`${n(t.credits_sold)} credits sold`} />
      </div>
      <Card>
        <h2 className="mb-4 font-serif text-2xl text-ink">Checks per day</h2>
        <Bars data={series} />
      </Card>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <h2 className="mb-3 font-semibold text-ink">Credits used, 30 days</h2>
          <div className="space-y-1 text-sm text-ink2">
            <div className="flex justify-between"><span>Personal (free)</span><span>{n(t.personal_credits_30d)}</span></div>
            <div className="flex justify-between"><span>Organisations</span><span>{n(t.org_credits_30d)}</span></div>
          </div>
          <h2 className="mt-5 mb-3 font-semibold text-ink">Provider calls, 30 days</h2>
          <ul className="space-y-1 text-sm">
            {stats.providers.map((p) => (
              <li key={p.provider} className="flex justify-between gap-3 text-ink2">
                <span className="text-ink">{p.provider}</span>
                <span>
                  {n(p.calls)} <span className="text-ink3">(cap {n(p.daily_cap)}/day)</span>
                </span>
              </li>
            ))}
          </ul>
        </Card>
        <Card>
          <h2 className="mb-3 font-semibold text-ink">Who signs up (survey)</h2>
          <ul className="space-y-2 text-sm">
            {answered.map((s) => (
              <li key={s.role ?? "none"} className="flex justify-between gap-3 text-ink2">
                <span className="text-ink">{s.role ? roleWords[s.role] ?? s.role : "Skipped this question"}</span>
                <span>{n(s.n)}</span>
              </li>
            ))}
          </ul>
          <div className="mt-3 text-xs text-ink3">
            {stats.survey
              .filter((s) => s.survey_state !== "answered")
              .map((s) => `${s.survey_state.replace("_", " ")}: ${s.n}`)
              .join(" · ")}
          </div>
        </Card>
      </div>
    </div>
  );
}

function Search({ onSearch, placeholder }: { onSearch: (q: string) => void; placeholder: string }) {
  const [q, setQ] = useState("");
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSearch(q.trim());
      }}
      className="mb-4 flex gap-2"
    >
      <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={placeholder} className="sm:max-w-sm" />
      <Button type="submit" variant="outline">
        Search
      </Button>
    </form>
  );
}

function CreditsModal({ title, url, onClose, onDone }: { title: string; url: string; onClose: () => void; onDone: () => void }) {
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <Modal open title={title} onClose={onClose}>
      <form
        className="space-y-4"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError(null);
          try {
            await api(url, { method: "POST", json: { amount: Number(amount), reason: reason.trim() }, account: "personal" });
            onDone();
            onClose();
          } catch (failure) {
            setError((failure as Error).message);
            setBusy(false);
          }
        }}
      >
        <Field label="Credits" hint="Negative to take credits away.">
          <Input type="number" required value={amount} onChange={(e) => setAmount(e.target.value)} />
        </Field>
        <Field label="Reason" hint="Kept in the audit log.">
          <Input required minLength={3} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Invoice INV-104 paid by bank transfer" />
        </Field>
        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" busy={busy} className="w-full">
          Apply
        </Button>
      </form>
    </Modal>
  );
}

function Orgs() {
  const [rows, setRows] = useState<AdminOrg[] | null>(null);
  const [q, setQ] = useState("");
  const [granting, setGranting] = useState<AdminOrg | null>(null);
  const load = useCallback(() => api<AdminOrg[]>(`/v1/admin/orgs?q=${encodeURIComponent(q)}`, { account: "personal" }).then(setRows), [q]);
  useEffect(() => {
    load();
  }, [load]);
  return (
    <>
      <Search onSearch={setQ} placeholder="Name or billing email" />
      {!rows ? (
        <Spinner />
      ) : (
        <Card className="p-0 sm:p-0">
          <Table head={["Organisation", "Credits", "Members", "Keys", "Created", ""]}>
            {rows.map((o) => (
              <tr key={o.id}>
                <td>
                  <Link href={`/app/org/${o.id}`} className="font-medium text-ink hover:underline">
                    {o.name}
                  </Link>
                  <div className="flex items-center gap-2 text-xs text-ink3">
                    {o.billing_email}
                    {o.status !== "active" && <Badge tone="bad">{o.status}</Badge>}
                  </div>
                </td>
                <td className="text-ink2">{n(o.balance)}</td>
                <td className="text-ink2">{n(o.members)}</td>
                <td className="text-ink2">{n(o.active_keys)}</td>
                <td className="whitespace-nowrap text-ink2">{when(o.created_at)}</td>
                <td className="text-right whitespace-nowrap">
                  <Button variant="ghost" size="sm" onClick={() => setGranting(o)}>
                    Credits
                  </Button>
                  {o.status !== "closed" && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className={o.status === "active" ? "text-false" : ""}
                      onClick={async () => {
                        const next = o.status === "active" ? "suspended" : "active";
                        const reason = prompt(`Why ${next === "suspended" ? "suspend" : "restore"} ${o.name}?`);
                        if (!reason) return;
                        await api(`/v1/admin/orgs/${o.id}/status`, { method: "POST", json: { status: next, reason }, account: "personal" });
                        load();
                      }}
                    >
                      {o.status === "active" ? "Suspend" : "Restore"}
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </Table>
        </Card>
      )}
      {granting && (
        <CreditsModal title={`Credits for ${granting.name}`} url={`/v1/admin/orgs/${granting.id}/credits`} onClose={() => setGranting(null)} onDone={load} />
      )}
    </>
  );
}

function People() {
  const { me } = useAccount();
  const [rows, setRows] = useState<AdminUser[] | null>(null);
  const [q, setQ] = useState("");
  const [granting, setGranting] = useState<AdminUser | null>(null);
  const load = useCallback(() => api<AdminUser[]>(`/v1/admin/users?q=${encodeURIComponent(q)}`, { account: "personal" }).then(setRows), [q]);
  useEffect(() => {
    load();
  }, [load]);
  return (
    <>
      <Search onSearch={setQ} placeholder="Email or name" />
      {!rows ? (
        <Spinner />
      ) : (
        <Card className="p-0 sm:p-0">
          <Table head={["Person", "Credits", "Organisations", "Joined", "Last seen", ""]}>
            {rows.map((u) => (
              <tr key={u.id}>
                <td>
                  <div className="font-medium text-ink">{u.name || u.email.split("@")[0]}</div>
                  <div className="flex flex-wrap items-center gap-1.5 text-xs text-ink3">
                    {u.email}
                    {u.is_staff && <Badge tone="acc">Staff</Badge>}
                    {u.disabled && <Badge tone="bad">Disabled</Badge>}
                  </div>
                </td>
                <td className="text-ink2">{n(u.balance)}</td>
                <td className="max-w-[180px] truncate text-ink2">{u.orgs || "—"}</td>
                <td className="whitespace-nowrap text-ink2">{when(u.created_at)}</td>
                <td className="whitespace-nowrap text-ink2">{ago(u.last_seen_at)}</td>
                <td className="text-right whitespace-nowrap">
                  <Button variant="ghost" size="sm" onClick={() => setGranting(u)}>
                    Credits
                  </Button>
                  {u.id !== me?.id && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className={u.disabled ? "" : "text-false"}
                      onClick={async () => {
                        if (!confirm(`${u.disabled ? "Enable" : "Disable"} ${u.email}?`)) return;
                        await api(`/v1/admin/users/${u.id}/disabled`, { method: "POST", json: { disabled: !u.disabled }, account: "personal" });
                        load();
                      }}
                    >
                      {u.disabled ? "Enable" : "Disable"}
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </Table>
        </Card>
      )}
      {granting && (
        <CreditsModal title={`Credits for ${granting.email}`} url={`/v1/admin/users/${granting.id}/credits`} onClose={() => setGranting(null)} onDone={load} />
      )}
    </>
  );
}

function Keys() {
  const [rows, setRows] = useState<AdminKey[] | null>(null);
  const [q, setQ] = useState("");
  const load = useCallback(() => api<AdminKey[]>(`/v1/admin/keys?q=${encodeURIComponent(q)}`, { account: "personal" }).then(setRows), [q]);
  useEffect(() => {
    load();
  }, [load]);
  return (
    <>
      <Search onSearch={setQ} placeholder="Key prefix (fct_live_…) or name" />
      {!rows ? (
        <Spinner />
      ) : (
        <Card className="p-0 sm:p-0">
          <Table head={["Key", "Organisation", "Created by", "Last used", ""]}>
            {rows.map((k) => (
              <tr key={k.id} className={k.revoked_at ? "opacity-60" : ""}>
                <td>
                  <div className="font-medium text-ink">{k.name}</div>
                  <div className="font-mono text-xs text-ink3">{k.prefix}…</div>
                </td>
                <td className="text-ink2">{k.org_name}</td>
                <td className="max-w-[200px] truncate text-ink2">{k.created_by_email}</td>
                <td className="whitespace-nowrap text-ink2">{ago(k.last_used_at)}</td>
                <td className="text-right">
                  {k.revoked_at ? (
                    <Badge tone="bad">Revoked</Badge>
                  ) : (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-false"
                      onClick={async () => {
                        if (!confirm(`Revoke ${k.prefix}… (${k.org_name})?`)) return;
                        await api(`/v1/admin/orgs/${k.org_id}/keys/${k.id}`, { method: "DELETE", account: "personal" });
                        load();
                      }}
                    >
                      Revoke
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </Table>
        </Card>
      )}
    </>
  );
}

function Audit() {
  const [rows, setRows] = useState<AuditRow[] | null>(null);
  useEffect(() => {
    api<AuditRow[]>("/v1/admin/audit", { account: "personal" }).then(setRows).catch(() => setRows([]));
  }, []);
  if (!rows) return <Spinner />;
  return (
    <Card className="p-0 sm:p-0">
      <Table head={["When", "Who", "Action", "Details"]}>
        {rows.map((r, i) => (
          <tr key={i}>
            <td className="whitespace-nowrap text-ink2">{when(r.at, true)}</td>
            <td className="max-w-[200px] truncate text-ink2">{r.actor_email || "system"}</td>
            <td className="text-ink">{r.action}</td>
            <td className="max-w-[320px] truncate text-xs text-ink3">{JSON.stringify(r.detail)}</td>
          </tr>
        ))}
      </Table>
    </Card>
  );
}
