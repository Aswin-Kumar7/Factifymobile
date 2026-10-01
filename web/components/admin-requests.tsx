"use client";

// Requests for an organisation plan, for Factify's admin to approve or reject.

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Avatar, Badge, Button, Card, Field, Input, Modal, Notice, Spinner, Table } from "./ui";
import { api } from "@/lib/api";
import { ago, n, when } from "@/lib/format";

type OrgRequestRow = {
  id: string;
  org_name: string;
  billing_email: string | null;
  use_case: string | null;
  expected_checks: number | null;
  website: string | null;
  status: "pending" | "approved" | "rejected" | "withdrawn";
  created_at: string;
  decided_at: string | null;
  decision_note: string | null;
  decided_by_email: string | null;
  org_id: string | null;
  email: string;
  name: string | null;
  personal_balance: number;
  personal_checks: number;
};

const tones = { pending: "warn", approved: "acc", rejected: "bad", withdrawn: "neutral" } as const;

export function AdminRequests() {
  const [rows, setRows] = useState<OrgRequestRow[] | null>(null);
  const [deciding, setDeciding] = useState<{ row: OrgRequestRow; approve: boolean } | null>(null);
  const [credits, setCredits] = useState("500");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => api<OrgRequestRow[]>("/v1/admin/org-requests", { account: "personal" }).then(setRows).catch(() => setRows([])), []);
  useEffect(() => {
    load();
  }, [load]);
  if (!rows) return <Spinner />;
  const pending = rows.filter((r) => r.status === "pending");
  const done = rows.filter((r) => r.status !== "pending");

  function open(row: OrgRequestRow, approve: boolean) {
    setDeciding({ row, approve });
    setNote("");
    setCredits("500");
    setError(null);
  }

  async function decide(e: React.FormEvent) {
    e.preventDefault();
    if (!deciding) return;
    setBusy(true);
    setError(null);
    try {
      await api(`/v1/admin/org-requests/${deciding.row.id}`, {
        method: "POST",
        json: {
          approve: deciding.approve,
          note: note.trim() || null,
          grant_credits: deciding.approve ? Number(credits || 0) : 0,
        },
        account: "personal",
      });
      setDeciding(null);
      load();
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      {pending.length === 0 ? (
        <Card>
          <p className="text-sm text-ink3">No requests waiting. New ones appear here.</p>
        </Card>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {pending.map((r) => (
            <Card key={r.id} className="flex flex-col">
              <div className="flex items-start gap-3">
                <Avatar name={r.org_name} size={44} />
                <div className="min-w-0 flex-1">
                  <div className="font-medium tracking-tight truncate text-2xl text-ink">{r.org_name}</div>
                  <div className="truncate text-sm text-ink2">
                    {r.name || r.email.split("@")[0]} · {r.email}
                  </div>
                </div>
                <Badge tone="warn">Waiting</Badge>
              </div>
              {r.use_case && <p className="mt-4 rounded-xl bg-sf2 p-3 text-[15px] text-ink">&ldquo;{r.use_case}&rdquo;</p>}
              <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                <dt className="text-ink3">Checks a month</dt>
                <dd className="tabular text-ink">{r.expected_checks != null ? n(r.expected_checks) : "—"}</dd>
                <dt className="text-ink3">Website</dt>
                <dd className="truncate text-ink">{r.website || "—"}</dd>
                <dt className="text-ink3">Billing email</dt>
                <dd className="truncate text-ink">{r.billing_email || "—"}</dd>
                <dt className="text-ink3">Their checks so far</dt>
                <dd className="tabular text-ink">{n(r.personal_checks)}</dd>
                <dt className="text-ink3">Asked</dt>
                <dd className="text-ink">{ago(r.created_at)}</dd>
              </dl>
              <div className="mt-5 flex gap-2">
                <Button onClick={() => open(r, true)}>Approve</Button>
                <Button variant="danger" onClick={() => open(r, false)}>
                  Reject
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}

      {done.length > 0 && (
        <Card className="p-0 sm:p-0">
          <h2 className="px-4 pt-4 font-semibold text-ink sm:px-5">Decided</h2>
          <Table head={["Organisation", "Asked by", "Decision", "By", "When"]}>
            {done.map((r) => (
              <tr key={r.id}>
                <td className="text-ink">
                  {r.org_id ? (
                    <Link href={`/app/admin/organisations/${r.org_id}`} className="font-medium hover:underline">
                      {r.org_name}
                    </Link>
                  ) : (
                    r.org_name
                  )}
                </td>
                <td className="max-w-[200px] truncate text-ink2">{r.email}</td>
                <td>
                  <Badge tone={tones[r.status]}>{r.status}</Badge>
                  {r.decision_note && <div className="mt-1 max-w-[240px] truncate text-xs text-ink3">{r.decision_note}</div>}
                </td>
                <td className="max-w-[180px] truncate text-ink2">{r.decided_by_email || "—"}</td>
                <td className="whitespace-nowrap text-ink2">{when(r.decided_at, true)}</td>
              </tr>
            ))}
          </Table>
        </Card>
      )}

      <Modal
        open={!!deciding}
        title={deciding ? `${deciding.approve ? "Approve" : "Reject"} ${deciding.row.org_name}` : ""}
        onClose={() => setDeciding(null)}
      >
        {deciding && (
          <form className="space-y-4" onSubmit={decide}>
            {deciding.approve ? (
              <>
                <p className="text-sm text-ink2">
                  Creates <b>{deciding.row.org_name}</b> with {deciding.row.email} as its owner.
                </p>
                <Field label="Starting credits" hint="Added to the new organisation's pool. 0 for none.">
                  <Input type="number" min={0} value={credits} onChange={(e) => setCredits(e.target.value)} />
                </Field>
              </>
            ) : (
              <p className="text-sm text-ink2">They&apos;ll see that the request wasn&apos;t approved, with your note.</p>
            )}
            <Field label={deciding.approve ? "Note (optional)" : "Reason"}>
              <Input
                required={!deciding.approve}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder={deciding.approve ? "Welcome aboard" : "We couldn't verify the organisation"}
              />
            </Field>
            {error && <Notice tone="error">{error}</Notice>}
            <Button type="submit" busy={busy} variant={deciding.approve ? "primary" : "danger"} className="w-full">
              {deciding.approve ? "Approve and create the organisation" : "Reject"}
            </Button>
          </form>
        )}
      </Modal>
    </div>
  );
}
