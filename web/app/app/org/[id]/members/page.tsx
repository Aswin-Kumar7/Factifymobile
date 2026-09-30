"use client";

import { useRouter } from "next/navigation";
import { use, useCallback, useEffect, useState } from "react";
import { useAccount } from "@/components/account";
import { Avatar, Badge, Button, Card, CopyButton, Field, Input, Modal, Notice, PageTitle, Progress, Select, Spinner, Table } from "@/components/ui";
import { api, Member, Role } from "@/lib/api";
import { ago, n, roleName, when } from "@/lib/format";
import { useOrg } from "@/lib/use-org";

type Invite = { id: string; email: string; role: Role; monthly_limit: number | null; expires_at: string; link?: string };

const roleHelp: Record<Role, string> = {
  owner: "Everything: billing, members, all keys and settings.",
  developer: "Checks, plus their own API keys.",
  member: "Checks within their limit.",
};

export default function Members({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { org } = useOrg(id);
  const { me, refresh } = useAccount();
  const router = useRouter();
  const [members, setMembers] = useState<Member[] | null>(null);
  const [invites, setInvites] = useState<Invite[]>([]);
  const [inviting, setInviting] = useState(false);
  const [editing, setEditing] = useState<Member | null>(null);
  const [error, setError] = useState<string | null>(null);
  const owner = org?.my_role === "owner";

  const load = useCallback(async () => {
    setMembers(await api<Member[]>(`/v1/orgs/${id}/members`, { account: "personal" }));
    if (owner) setInvites(await api<Invite[]>(`/v1/orgs/${id}/invites`, { account: "personal" }).catch(() => []));
  }, [id, owner]);
  useEffect(() => {
    if (org) load().catch((e: Error) => setError(e.message));
  }, [org, load]);

  async function remove(m: Member) {
    const self = m.user_id === me?.id;
    const question = self
      ? `Leave ${org?.name}?`
      : `Remove ${m.email} from ${org?.name}? Their API keys will be revoked.`;
    if (!confirm(question)) return;
    try {
      await api(`/v1/orgs/${id}/members/${m.user_id}`, { method: "DELETE", account: "personal" });
      if (self) {
        await refresh();
        router.push("/app/check");
      } else load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  if (!org || !members) return <Spinner />;

  return (
    <>
      <PageTitle
        eyebrow={org.name}
        title="Members"
        sub={owner ? "Invite people, choose what they can do, and cap what they spend." : `People in ${org.name}.`}
        action={owner && <Button onClick={() => setInviting(true)}>Invite someone</Button>}
      />
      {error && (
        <div className="mb-4">
          <Notice tone="error">{error}</Notice>
        </div>
      )}

      <Card className="p-0 sm:p-0">
        <Table head={["Person", "Role", owner ? "This month / limit" : "", owner ? "Activity" : "", ""]}>
          {members.map((m) => (
            <tr key={m.user_id}>
              <td>
                <div className="flex items-center gap-3">
                  <Avatar name={m.name || m.email} />
                  <div className="min-w-0">
                    <div className="truncate font-medium text-ink">{m.name || m.email.split("@")[0]}</div>
                    <div className="truncate text-xs text-ink3">{m.email}</div>
                  </div>
                </div>
              </td>
              <td>
                <div className="flex flex-wrap gap-1.5">
                  <Badge tone={m.role === "owner" ? "acc" : "neutral"}>{roleName[m.role]}</Badge>
                  {m.status !== "active" && <Badge tone="warn">Suspended</Badge>}
                </div>
              </td>
              <td className="min-w-[150px] text-ink2">
                {owner && m.month_spend != null && (
                  <>
                    <div className="tabular text-sm">
                      {n(m.month_spend)}
                      {m.monthly_limit != null && <span className="text-ink3"> / {n(m.monthly_limit)}</span>}
                    </div>
                    <div className="mt-1.5">
                      <Progress used={Number(m.month_spend)} total={m.monthly_limit} />
                    </div>
                  </>
                )}
              </td>
              <td className="whitespace-nowrap text-ink2">
                {owner && (
                  <>
                    <div className="tabular text-sm">{n(m.lifetime_spend)} all time</div>
                    <div className="text-xs text-ink3">last check {ago(m.last_active_at)}</div>
                  </>
                )}
              </td>
              <td className="text-right whitespace-nowrap">
                {owner && (
                  <Button variant="ghost" size="sm" onClick={() => setEditing(m)}>
                    Edit
                  </Button>
                )}
                {(owner || m.user_id === me?.id) && (
                  <Button variant="ghost" size="sm" className="text-false" onClick={() => remove(m)}>
                    {m.user_id === me?.id ? "Leave" : "Remove"}
                  </Button>
                )}
              </td>
            </tr>
          ))}
        </Table>
      </Card>

      {owner && invites.length > 0 && (
        <>
          <h2 className="mt-8 mb-3 font-serif text-2xl text-ink">Open invitations</h2>
          <Card className="p-0 sm:p-0">
            <Table head={["Email", "Role", "Limit", "Expires", ""]}>
              {invites.map((i) => (
                <tr key={i.id}>
                  <td className="text-ink">{i.email}</td>
                  <td>{roleName[i.role]}</td>
                  <td className="text-ink2">{i.monthly_limit != null ? n(i.monthly_limit) : "No limit"}</td>
                  <td className="text-ink2">{when(i.expires_at)}</td>
                  <td className="text-right">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-false"
                      onClick={async () => {
                        await api(`/v1/orgs/${id}/invites/${i.id}`, { method: "DELETE", account: "personal" });
                        load();
                      }}
                    >
                      Withdraw
                    </Button>
                  </td>
                </tr>
              ))}
            </Table>
          </Card>
        </>
      )}

      <InviteModal open={inviting} orgId={id} onClose={() => setInviting(false)} onDone={load} />
      {editing && <EditModal member={editing} orgId={id} onClose={() => setEditing(null)} onDone={load} />}
    </>
  );
}

function RoleChoice({ value, onChange }: { value: Role; onChange: (r: Role) => void }) {
  return (
    <div className="space-y-2">
      {(["member", "developer", "owner"] as Role[]).map((r) => (
        <label key={r} className={`flex cursor-pointer gap-3 rounded-xl border p-3 ${value === r ? "border-acc bg-acc-soft" : "border-line"}`}>
          <input type="radio" name="role" checked={value === r} onChange={() => onChange(r)} className="mt-1 accent-[var(--acc)]" />
          <span>
            <span className="block font-semibold text-ink">{roleName[r]}</span>
            <span className="block text-sm text-ink2">{roleHelp[r]}</span>
          </span>
        </label>
      ))}
    </div>
  );
}

function InviteModal({ open, orgId, onClose, onDone }: { open: boolean; orgId: string; onClose: () => void; onDone: () => void }) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("member");
  const [limit, setLimit] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [link, setLink] = useState<string | null>(null);

  function close() {
    setEmail("");
    setLimit("");
    setRole("member");
    setLink(null);
    setError(null);
    onClose();
  }

  async function send(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const invite = await api<Invite>(`/v1/orgs/${orgId}/invites`, {
        method: "POST",
        json: { email: email.trim(), role, monthly_limit: limit ? Number(limit) : null },
        account: "personal",
      });
      setLink(invite.link ?? null);
      onDone();
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open={open} title="Invite someone" onClose={close}>
      {link ? (
        <div className="space-y-4">
          <Notice tone="success">Invitation created for {email}. Send them this link; it works for 21 days.</Notice>
          <div className="rounded-xl bg-sf2 p-3 font-mono text-xs break-all text-ink">{link}</div>
          <div className="flex gap-2">
            <CopyButton text={link} label="Copy link" />
            <Button variant="ghost" size="sm" onClick={close}>
              Done
            </Button>
          </div>
        </div>
      ) : (
        <form onSubmit={send} className="space-y-4">
          <Field label="Email">
            <Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="colleague@example.com" />
          </Field>
          <RoleChoice value={role} onChange={setRole} />
          <Field label="Monthly credit limit" hint="Leave empty for no limit beyond the pool.">
            <Input type="number" min={0} value={limit} onChange={(e) => setLimit(e.target.value)} placeholder="e.g. 500" />
          </Field>
          {error && <Notice tone="error">{error}</Notice>}
          <Button type="submit" busy={busy} className="w-full">
            Create invitation
          </Button>
        </form>
      )}
    </Modal>
  );
}

function EditModal({ member, orgId, onClose, onDone }: { member: Member; orgId: string; onClose: () => void; onDone: () => void }) {
  const [role, setRole] = useState<Role>(member.role);
  const [limit, setLimit] = useState(member.monthly_limit != null ? String(member.monthly_limit) : "");
  const [status, setStatus] = useState(member.status);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api(`/v1/orgs/${orgId}/members/${member.user_id}`, {
        method: "PATCH",
        json: {
          role,
          status,
          ...(limit === "" ? { clear_limit: true } : { monthly_limit: Number(limit) }),
        },
        account: "personal",
      });
      onDone();
      onClose();
    } catch (failure) {
      setError((failure as Error).message);
      setBusy(false);
    }
  }

  return (
    <Modal open title={member.name || member.email} onClose={onClose}>
      <form onSubmit={save} className="space-y-4">
        <RoleChoice value={role} onChange={setRole} />
        <Field label="Monthly credit limit" hint="Leave empty for no limit beyond the pool.">
          <Input type="number" min={0} value={limit} onChange={(e) => setLimit(e.target.value)} />
        </Field>
        <Field label="Status" hint="A suspended member can't check or use their keys.">
          <Select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="active">Active</option>
            <option value="suspended">Suspended</option>
          </Select>
        </Field>
        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" busy={busy} className="w-full">
          Save
        </Button>
      </form>
    </Modal>
  );
}
