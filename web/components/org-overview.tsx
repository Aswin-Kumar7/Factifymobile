"use client";

// An organisation at a glance: its pool, this month against its cap, activity,
// who spends and through which keys. Owners and Factify admins see everything;
// developers and members see the pool and their own share.

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { AreaChart, daily, Ring, Sparkline, Split } from "./charts";
import { Icon } from "./shell";
import { Avatar, Badge, Button, Card, Field, Input, Modal, Notice, Progress, Spinner, Stat } from "./ui";
import { api, Member, Org, Usage } from "@/lib/api";
import { ago, inr, n, roleName, when } from "@/lib/format";

export type OrgDetail = Org & {
  credits_added: number;
  lifetime_spend: number;
  lifetime_checks: number;
  paid_paise: number;
  last_check_at: string | null;
  viewing_as_staff?: boolean;
};

export function OrgOverview({ id, admin = false, base }: { id: string; admin?: boolean; base: string }) {
  const [org, setOrg] = useState<OrgDetail | null>(null);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [o, u, m] = await Promise.all([
        api<OrgDetail>(`/v1/orgs/${id}`, { account: "personal" }),
        api<Usage>(`/v1/orgs/${id}/usage?days=30`, { account: "personal" }),
        api<Member[]>(`/v1/orgs/${id}/members`, { account: "personal" }),
      ]);
      setOrg(o);
      setUsage(u);
      setMembers(m);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [id]);
  useEffect(() => {
    load();
  }, [load]);

  if (error) return <Notice tone="error">{error}</Notice>;
  if (!org || !usage) return <Spinner />;

  const full = admin || org.my_role === "owner";
  const available = org.balance - org.held;
  const series = daily(usage.by_day, 30);
  const checks = daily(usage.by_day, 30, "checks");
  const spark = series.map((p) => p.value);
  const month = org.month_spend;
  const cap = org.monthly_spend_limit;
  const owners = members.filter((m) => m.role === "owner");
  const byRole = (["owner", "developer", "member"] as const).map((r) => ({
    label: `${roleName[r]}s`,
    value: members.filter((m) => m.role === r).length,
  }));
  const keyShare = usage.by_key.reduce((s, k) => s + Number(k.credits), 0);
  const webShare = Math.max(0, month - keyShare);

  return (
    <div className="space-y-6">
      {org.alerts.length > 0 && (
        <div className="space-y-2">
          {org.alerts.map((a) => (
            <Notice key={a.text} tone={a.level}>
              {a.text}
            </Notice>
          ))}
        </div>
      )}

      {/* The pool: what is left, and this month against the cap. */}
      <section className="paper relative overflow-hidden rounded-[16px] border border-line bg-sf p-5 shadow-card sm:p-7">
        <div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={org.status === "active" ? "acc" : "bad"}>{org.status === "active" ? "Active" : org.status}</Badge>
              <span className="text-sm text-ink3">since {when(org.created_at)}</span>
            </div>
            <div className="mt-4 text-sm font-medium text-ink3">Credits available</div>
            <div className="tabular text-6xl leading-none font-medium tracking-tight text-ink sm:text-7xl">{n(available)}</div>
            <div className="mt-2 text-sm text-ink2">
              {org.held > 0 && <>{n(org.held)} held by checks running now · </>}
              {n(org.credits_added)} added in total · {n(org.lifetime_spend)} used
            </div>
            <div className="mt-5 flex flex-wrap gap-2">
              {!admin && (
                <Link href="/app/check" className="inline-flex items-center gap-1.5 rounded-[9px] bg-acc px-4 py-2.5 text-sm font-semibold text-on-acc hover:bg-acc-h">
                  <Icon name="bolt" size={16} /> Check something
                </Link>
              )}
              {full && !admin && (
                <Link href={`${base}/billing`} className="rounded-xl border border-line bg-sf px-4 py-2.5 text-sm font-semibold text-ink hover:bg-sf2">
                  Buy credits
                </Link>
              )}
              {admin && <AdminActions org={org} onDone={load} />}
            </div>
          </div>
          <div className="flex items-center gap-5">
            <Ring
              used={month}
              total={cap ?? Math.max(month, available + month, 1)}
              label={n(month)}
              sub={cap != null ? `of ${n(cap)} cap` : "this month"}
            />
            <div className="hidden text-sm sm:block">
              <div className="text-ink3">This month</div>
              <div className="tabular text-ink">{n(month)} credits</div>
              <div className="mt-2 text-ink3">Monthly cap</div>
              <div className="tabular text-ink">{cap != null ? n(cap) : "None"}</div>
              <div className="mt-2 text-ink3">Last check</div>
              <div className="text-ink">{ago(org.last_check_at)}</div>
            </div>
          </div>
        </div>
      </section>

      <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
        <Stat label="Used, 30 days" value={n(spark.reduce((s, v) => s + v, 0))} icon={<Icon name="usage" size={17} />} tone="acc" trend={<Sparkline values={spark} />} />
        <Stat label="Checks, all time" value={n(org.lifetime_checks)} icon={<Icon name="check" size={17} />} trend={<Sparkline values={checks.map((p) => p.value)} />} />
        <Stat label="Members" value={n(org.members)} sub={`${owners.length} owner${owners.length === 1 ? "" : "s"}`} icon={<Icon name="members" size={17} />} />
        <Stat
          label={full ? "Paid" : "Active API keys"}
          value={full ? inr(org.paid_paise / 100) : n(org.active_keys)}
          sub={full ? `${n(org.active_keys)} active keys` : undefined}
          icon={<Icon name={full ? "billing" : "keys"} size={17} />}
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
        <Card>
          <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
            <div>
              <h2 className="font-medium tracking-tight text-2xl text-ink">{full ? "Credits used" : "Your credits used"}</h2>
              <p className="text-sm text-ink3">Last 30 days</p>
            </div>
            <Link href={`${base}/usage`} className="text-sm font-semibold text-acc-ink">
              Full usage →
            </Link>
          </div>
          <AreaChart data={series} />
        </Card>
        <Card>
          <h2 className="font-medium tracking-tight text-2xl text-ink">Where it goes</h2>
          <p className="mb-4 text-sm text-ink3">This month</p>
          <Split
            parts={[
              { label: "Dashboard and app", value: webShare },
              { label: "API keys", value: keyShare },
            ]}
          />
          <h3 className="mt-6 mb-3 text-sm font-semibold text-ink">Team</h3>
          <Split parts={byRole} />
        </Card>
      </div>

      {full && (
        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <div className="mb-4 flex items-baseline justify-between">
              <h2 className="font-medium tracking-tight text-2xl text-ink">Members this month</h2>
              <Link href={`${base}/members`} className="text-sm font-semibold text-acc-ink">
                Manage →
              </Link>
            </div>
            <ul className="space-y-4">
              {[...members]
                .sort((a, b) => Number(b.month_spend ?? 0) - Number(a.month_spend ?? 0))
                .slice(0, 6)
                .map((m) => (
                  <li key={m.user_id} className="flex items-center gap-3">
                    <Avatar name={m.name || m.email} />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate text-sm font-semibold text-ink">{m.name || m.email.split("@")[0]}</span>
                        <span className="tabular shrink-0 text-xs text-ink2">
                          {n(m.month_spend)}
                          {m.monthly_limit != null ? ` / ${n(m.monthly_limit)}` : ""}
                        </span>
                      </div>
                      <div className="mt-1.5">
                        <Progress used={Number(m.month_spend ?? 0)} total={m.monthly_limit ?? Math.max(1, ...members.map((x) => Number(x.month_spend ?? 0)))} />
                      </div>
                      <div className="mt-1 text-[11px] text-ink3">
                        {roleName[m.role]}
                        {m.status !== "active" && " · suspended"} · last check {ago(m.last_active_at)}
                      </div>
                    </div>
                  </li>
                ))}
            </ul>
          </Card>
          <Card>
            <div className="mb-4 flex items-baseline justify-between">
              <h2 className="font-medium tracking-tight text-2xl text-ink">API keys this month</h2>
              <Link href={`${base}/keys`} className="text-sm font-semibold text-acc-ink">
                Manage →
              </Link>
            </div>
            {usage.by_key.length ? (
              <ul className="space-y-4">
                {usage.by_key.slice(0, 6).map((k) => (
                  <li key={k.key_id}>
                    <div className="flex items-center justify-between gap-2 text-sm">
                      <span className="min-w-0 truncate font-semibold text-ink">
                        {k.name} <span className="font-mono text-xs font-normal text-ink3">{k.prefix}…</span>
                      </span>
                      <span className="tabular shrink-0 text-xs text-ink2">
                        {n(k.credits)} · {n(k.checks)} calls
                      </span>
                    </div>
                    <div className="mt-1.5">
                      <Progress used={Number(k.credits)} total={Math.max(1, ...usage.by_key.map((x) => Number(x.credits)))} />
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="rounded-xl border border-dashed border-line px-4 py-8 text-center text-sm text-ink3">No API calls in the last 30 days.</div>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}

/** What only Factify's admin can do to an organisation. */
function AdminActions({ org, onDone }: { org: OrgDetail; onDone: () => void }) {
  const [open, setOpen] = useState<"credits" | "cap" | null>(null);
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [cap, setCap] = useState(org.monthly_spend_limit != null ? String(org.monthly_spend_limit) : "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      setOpen(null);
      setAmount("");
      setReason("");
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Button onClick={() => setOpen("credits")}>Add or remove credits</Button>
      <Button variant="outline" onClick={() => setOpen("cap")}>
        Monthly cap
      </Button>
      {org.status !== "closed" && (
        <Button
          variant={org.status === "active" ? "danger" : "outline"}
          onClick={() => {
            const next = org.status === "active" ? "suspended" : "active";
            const why = prompt(`Why ${next === "suspended" ? "suspend" : "restore"} ${org.name}? (kept in the audit log)`);
            if (why) run(() => api(`/v1/admin/orgs/${org.id}/status`, { method: "POST", json: { status: next, reason: why }, account: "personal" }));
          }}
        >
          {org.status === "active" ? "Suspend" : "Restore"}
        </Button>
      )}
      <Modal open={open === "credits"} title={`Credits for ${org.name}`} onClose={() => setOpen(null)}>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            run(() => api(`/v1/admin/orgs/${org.id}/credits`, { method: "POST", json: { amount: Number(amount), reason: reason.trim() }, account: "personal" }));
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
      <Modal open={open === "cap"} title="Monthly spending cap" onClose={() => setOpen(null)}>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            run(() =>
              api(`/v1/orgs/${org.id}`, {
                method: "PATCH",
                json: cap === "" ? { clear_spend_limit: true } : { monthly_spend_limit: Number(cap) },
                account: "personal",
              }),
            );
          }}
        >
          <Field label="Credits a month" hint="Empty: no cap. Checks past the cap are refused.">
            <Input type="number" min={0} value={cap} onChange={(e) => setCap(e.target.value)} />
          </Field>
          {error && <Notice tone="error">{error}</Notice>}
          <Button type="submit" busy={busy} className="w-full">
            Save
          </Button>
        </form>
      </Modal>
    </>
  );
}
