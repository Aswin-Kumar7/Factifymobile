"use client";

import { use, useEffect, useState } from "react";
import { auditAction, auditDetail } from "@/components/org-audit";
import { Card, Empty, Notice, PageTitle, Spinner, Table } from "@/components/ui";
import { api } from "@/lib/api";
import { when } from "@/lib/format";
import { useOrg } from "@/lib/use-org";

type Entry = { at: string; action: string; target: string | null; detail: Record<string, unknown>; actor_email: string | null };

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
                  {auditAction(e.action)}
                  {e.target && e.target.includes("@") && <span className="text-ink3"> {e.target}</span>}
                </td>
                <td className="max-w-[280px] truncate text-xs text-ink3">{auditDetail(e.detail)}</td>
              </tr>
            ))}
          </Table>
        </Card>
      )}
    </>
  );
}
