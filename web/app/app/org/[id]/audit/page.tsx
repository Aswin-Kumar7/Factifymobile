"use client";

import { use, useEffect, useState } from "react";
import { Card, Empty, Notice, PageTitle, Spinner, Table } from "@/components/ui";
import { api } from "@/lib/api";
import { when } from "@/lib/format";
import { useOrg } from "@/lib/use-org";

type Entry = { at: string; action: string; target: string | null; detail: Record<string, unknown>; actor_email: string | null };

const words: Record<string, string> = {
  "org.created": "Created the organisation",
  "org.updated": "Changed settings",
  "org.closed": "Closed the organisation",
  "member.updated": "Changed a member",
  "member.removed": "Removed a member",
  "member.joined_by_domain": "Joined through the verified domain",
  "invite.created": "Invited",
  "invite.revoked": "Withdrew an invitation",
  "invite.accepted": "Accepted an invitation",
  "key.created": "Created an API key",
  "key.updated": "Changed an API key",
  "key.rotated": "Rotated an API key",
  "key.revoked": "Revoked an API key",
  "credits.purchase": "Bought credits",
  "credits.grant": "Factify added credits",
  "credits.adjustment": "Factify adjusted credits",
  "domain.added": "Added a domain",
  "domain.updated": "Changed a domain",
  "domain.removed": "Removed a domain",
  "admin.org_suspended": "Factify suspended the organisation",
  "admin.org_active": "Factify restored the organisation",
};

function describe(detail: Record<string, unknown>) {
  return Object.entries(detail || {})
    .filter(([, v]) => v !== null && v !== "")
    .map(([k, v]) => `${k.replace(/_/g, " ")}: ${String(v)}`)
    .join(", ");
}

export default function Audit({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { org, error } = useOrg(id);
  const [entries, setEntries] = useState<Entry[] | null>(null);

  useEffect(() => {
    api<Entry[]>(`/v1/orgs/${id}/audit`, { account: "personal" }).then(setEntries).catch(() => setEntries([]));
  }, [id]);

  if (error) return <Notice tone="error">{error}</Notice>;
  if (!org) return <Spinner />;
  if (org.my_role !== "owner") return <Notice tone="info">Only owners can see the audit log.</Notice>;

  return (
    <>
      <PageTitle eyebrow={org.name} title="Audit log" sub="Who changed what, and when." />
      {!entries ? (
        <Spinner />
      ) : entries.length === 0 ? (
        <Empty title="Nothing yet" />
      ) : (
        <Card className="p-0 sm:p-0">
          <Table head={["When", "Who", "What", "Details"]}>
            {entries.map((e, i) => (
              <tr key={i}>
                <td className="whitespace-nowrap text-ink2">{when(e.at, true)}</td>
                <td className="max-w-[200px] truncate text-ink2">{e.actor_email || "Factify"}</td>
                <td className="text-ink">
                  {words[e.action] ?? e.action}
                  {e.target && e.target.includes("@") && <span className="text-ink3"> {e.target}</span>}
                </td>
                <td className="max-w-[280px] truncate text-xs text-ink3">{describe(e.detail)}</td>
              </tr>
            ))}
          </Table>
        </Card>
      )}
    </>
  );
}
