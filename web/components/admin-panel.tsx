"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useAccount } from "@/components/account";
import { AdminRequests } from "@/components/admin-requests";
import { AreaChart, daily, Split } from "@/components/charts";
import { Icon } from "@/components/shell";
import { Avatar, Badge, Button, Card, Field, Input, Modal, Notice, PageTitle, Progress, Spinner, Stat, Table } from "@/components/ui";
import { api } from "@/lib/api";
import { ago, inr, n, when } from "@/lib/format";

type Stats = {
  totals: Record<string, number>;
  by_day: { day: string; checks: number; videos: number }[];
  providers: { provider: string; calls: number; daily_cap: number }[];
  survey: { survey_state: string; role: string | null; n: number }[];
};
type AdminOrg = { id: string; name: string; status: string; created_at: string; billing_email: string | null; balance: number; members: number; active_keys: number; plan?: string; seats?: number };
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
  plan?: string;
  orgs: string | null;
};
type AdminKey = { id: string; org_id: string; org_name: string; name: string; prefix: string; created_at: string; last_used_at: string | null; revoked_at: string | null; created_by_email: string | null };
type AuditRow = { at: string; action: string; target: string | null; detail: Record<string, unknown>; actor_email: string | null };

const roleWords: Record<string, string> = {
  journalist: "Journalists",
  student: "Students",
  teacher: "Teachers",
  family: "Checking for family",
  curious: "Curious",
};

export type Section = "Overview" | "Requests" | "Organisations" | "People" | "API keys" | "Audit";

export function AdminSection({ section }: { section: Section }) {
  const { me } = useAccount();
  if (!me?.is_staff) return <Notice tone="info">This page is for the Factify team.</Notice>;
  const subs: Record<Section, string> = {
    Overview: "Everything on Factify at a glance.",
    Requests: "People asking for an organisation plan. Approving creates the organisation with them as owner.",
    Organisations: "Every organisation: credits, members, keys. Add credits or suspend.",
    People: "Everyone with an account. Add credits or disable.",
    "API keys": "Find any key by its prefix or name, and revoke it.",
    Audit: "Admin and billing actions, newest first.",
  };
  return (
    <>
      <PageTitle eyebrow="Factify admin" title={section === "Overview" ? "Platform" : section} sub={subs[section]} />
      {section === "Overview" && <Overview />}
      {section === "Requests" && <AdminRequests />}
      {section === "Organisations" && <Orgs />}
      {section === "People" && <People />}
      {section === "API keys" && <Keys />}
      {section === "Audit" && <Audit />}
    </>
  );
}

function Overview() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [orgs, setOrgs] = useState<AdminOrg[]>([]);
  useEffect(() => {
    api<Stats>("/v1/admin/stats", { account: "personal" }).then(setStats).catch(() => undefined);
    api<AdminOrg[]>("/v1/admin/orgs", { account: "personal" }).then(setOrgs).catch(() => undefined);
  }, []);
  if (!stats) return <Spinner />;
  const t = stats.totals;
  const series = daily(stats.by_day, 30, "checks");
  const videos = new Map(stats.by_day.map((d) => [d.day, Number(d.videos)]));
  const withVideos = series.map((p, i) => {
    const d = new Date(Date.now() - (29 - i) * 86400000).toISOString().slice(0, 10);
    return { ...p, extra: videos.get(d) ?? 0 };
  });
  const answered = stats.survey.filter((s) => s.survey_state === "answered");
  const maxCalls = Math.max(1, ...stats.providers.map((p) => Number(p.calls)));
  const lowOrgs = orgs.filter((o) => o.status === "active" && o.balance < 50);
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
        <Stat label="People" value={n(t.users)} sub={`${n(t.users_7d)} new this week`} icon={<Icon name="members" size={17} />} tone="acc" />
        <Stat label="Organisations" value={n(t.orgs)} sub={`${n(t.active_keys)} active API keys`} icon={<Icon name="building" size={17} />} />
        <Stat label="Checks, 24 h" value={n(t.checks_24h)} sub={`${n(t.checks_30d)} in 30 days`} icon={<Icon name="check" size={17} />} />
        <Stat label="Revenue" value={inr((t.revenue_paise ?? 0) / 100)} sub={`${n(t.paid_plans ?? 0)} paid ${(t.paid_plans ?? 0) === 1 ? "plan" : "plans"} · ${n(t.credits_sold)} credits sold`} icon={<Icon name="billing" size={17} />} tone="warn" />
      </div>

      <Card>
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="font-medium tracking-tight text-2xl text-ink">Checks per day</h2>
            <p className="text-sm text-ink3">Last 30 days, every account</p>
          </div>
          <div className="flex items-center gap-4 text-xs text-ink2">
            <span className="flex items-center gap-1.5">
              <span className="h-0.5 w-4 bg-chart-1" /> All checks
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-0.5 w-4 border-t-2 border-dashed border-chart-3" /> Videos
            </span>
          </div>
        </div>
        <AreaChart data={withVideos} unit="checks" extraLabel="videos" />
      </Card>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card>
          <h2 className="font-medium tracking-tight text-xl text-ink">Credits used</h2>
          <p className="mb-4 text-sm text-ink3">Last 30 days</p>
          <Split
            parts={[
              { label: "Free (personal)", value: Number(t.personal_credits_30d) },
              { label: "Organisations", value: Number(t.org_credits_30d) },
            ]}
          />
        </Card>
        <Card>
          <h2 className="font-medium tracking-tight text-xl text-ink">Provider calls</h2>
          <p className="mb-4 text-sm text-ink3">Last 30 days: what checks cost us</p>
          <ul className="space-y-3">
            {stats.providers.map((p) => (
              <li key={p.provider}>
                <div className="flex justify-between gap-3 text-sm">
                  <span className="font-medium text-ink">{p.provider.replace("_", " ")}</span>
                  <span className="tabular text-ink2">{n(p.calls)}</span>
                </div>
                <div className="mt-1.5">
                  <Progress used={Number(p.calls)} total={maxCalls} />
                </div>
                <div className="mt-0.5 text-[11px] text-ink3">{p.daily_cap >= 1e9 ? "no daily cap" : `cap ${n(p.daily_cap)} a day`}</div>
              </li>
            ))}
          </ul>
        </Card>
        <Card>
          <h2 className="font-medium tracking-tight text-xl text-ink">Who signs up</h2>
          <p className="mb-4 text-sm text-ink3">From the new-account survey</p>
          <Split parts={answered.map((s) => ({ label: s.role ? roleWords[s.role] ?? s.role : "Skipped", value: Number(s.n) }))} />
          <div className="mt-3 text-xs text-ink3">
            {stats.survey
              .filter((s) => s.survey_state !== "answered")
              .map((s) => `${s.survey_state.replace("_", " ")}: ${s.n}`)
              .join(" · ")}
          </div>
        </Card>
      </div>

      <Card>
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="font-medium tracking-tight text-xl text-ink">Needs attention</h2>
          <Link href="/app/admin/organisations" className="text-sm font-semibold text-acc-ink">
            All organisations →
          </Link>
        </div>
        {lowOrgs.length ? (
          <ul className="divide-y divide-line">
            {lowOrgs.slice(0, 6).map((o) => (
              <li key={o.id}>
                <Link href={`/app/admin/organisations/${o.id}`} className="flex items-center gap-3 py-2.5 hover:opacity-80">
                  <Avatar name={o.name} size={32} />
                  <span className="min-w-0 flex-1 truncate font-medium text-ink">{o.name}</span>
                  <Badge tone={o.balance <= 0 ? "bad" : "warn"}>{o.balance <= 0 ? "Out of credits" : `${n(o.balance)} left`}</Badge>
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-ink3">Every active organisation has at least 50 credits.</p>
        )}
      </Card>
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
          <Table head={["Organisation", "Plan", "Credits", "Members", "Keys", "Created", ""]}>
            {rows.map((o) => (
              <tr key={o.id}>
                <td>
                  <Link href={`/app/admin/organisations/${o.id}`} className="flex items-center gap-3 font-medium text-ink hover:underline">
                    <Avatar name={o.name} size={32} />
                    {o.name}
                  </Link>
                  <div className="flex items-center gap-2 text-xs text-ink3">
                    {o.billing_email}
                    {o.status !== "active" && <Badge tone="bad">{o.status}</Badge>}
                  </div>
                </td>
                <td className="whitespace-nowrap text-ink2">{o.plan === "team" ? `Team · ${n(o.seats)}` : o.plan === "api" ? "API" : "Packs"}</td>
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
          <Table head={["Person", "Plan", "Credits", "Organisations", "Joined", "Last seen", ""]}>
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
                <td className="text-ink2 capitalize">{u.plan ?? "free"}</td>
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
