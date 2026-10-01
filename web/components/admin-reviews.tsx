"use client";

// Reported and held cases, for Factify's admin: what someone pressed "Report wrong
// result" on (POST /v1/cases/{id}/report), and what the system declined to decide.
// The admin opens the result, then records a label beside the machine's verdict
// (POST /v1/review/{item_id}); the machine's own verdict is never overwritten.

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Badge, Button, Card, Field, Input, Modal, Notice, Select, Spinner, Table } from "./ui";
import { useAccount } from "./account";
import { api } from "@/lib/api";
import { ago, when } from "@/lib/format";

type ReviewRow = {
  item_id: string;
  case_id: string;
  reason: string;
  machine_status: string | null;
  human_label: string | null;
  reviewer: string | null;
  notes: string | null;
  created_at: string;
  reviewed_at: string | null;
  input_type: string;
  overall_action: string | null;
  case_status: string;
  checked_at: string;
  title: string | null;
  open_reports: number;
};

const reasons: Record<string, string> = {
  user_reported: "Reported by someone",
  no_citable_evidence: "No evidence to cite",
  sources_disagree: "Sources disagree",
  publisher_risk_signals: "Publisher risk",
  checks_could_not_run: "Checks couldn't run",
  story_still_developing: "Story still developing",
};

const labels: Record<string, string> = {
  SUPPORTED: "True (supported)",
  CONTRADICTED: "False (contradicted)",
  MISLEADING_CONTEXT: "Misleading or missing context",
  UNVERIFIED: "Can't be verified",
  OUT_OF_SCOPE: "Not a checkable claim",
};

const actions: Record<string, string> = {
  SAFE_TO_SHARE: "Safe to share",
  SHARE_WITH_CONTEXT: "Share with context",
  SHARE_WITH_CORRECTION: "Share with a correction",
  DO_NOT_SHARE: "Don't share",
  WAIT_AND_RECHECK: "Wait and recheck",
  SEND_TO_REVIEW: "Sent to review",
};

const kinds: Record<string, string> = { text: "Text", url: "Link", image: "Picture", pdf: "PDF", video: "Video" };

export function AdminReviews() {
  const { me } = useAccount();
  const [tab, setTab] = useState<"pending" | "reviewed">("pending");
  const [rows, setRows] = useState<ReviewRow[] | null>(null);
  const [labelling, setLabelling] = useState<ReviewRow | null>(null);
  const [label, setLabel] = useState("CONTRADICTED");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setRows(null);
    return api<ReviewRow[]>(`/v1/admin/reviews?status=${tab}`, { account: "personal" })
      .then(setRows)
      .catch((e: Error) => {
        setError(e.message);
        setRows([]);
      });
  }, [tab]);
  useEffect(() => {
    load();
  }, [load]);

  async function record(e: React.FormEvent) {
    e.preventDefault();
    if (!labelling || !me) return;
    setBusy(true);
    setError(null);
    try {
      await api(`/v1/review/${labelling.item_id}`, {
        method: "POST",
        json: { label, reviewer: me.email, notes: notes.trim() || null },
        account: "personal",
      });
      setLabelling(null);
      await load();
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <div role="tablist" aria-label="Reports" className="inline-flex rounded-[9px] border border-line bg-sf p-[3px]">
        {(["pending", "reviewed"] as const).map((t) => (
          <button
            key={t}
            type="button"
            role="tab"
            aria-selected={tab === t}
            onClick={() => setTab(t)}
            className={`rounded-[7px] px-3 py-1.5 text-[13px] ${tab === t ? "bg-hover text-ink" : "text-ink2 hover:text-ink"}`}
          >
            {t === "pending" ? "Waiting" : "Reviewed"}
          </button>
        ))}
      </div>
      {error && !labelling && <Notice tone="error">{error}</Notice>}
      {!rows ? (
        <Spinner />
      ) : rows.length === 0 ? (
        <Card>
          <p className="text-sm text-ink3">{tab === "pending" ? "Nothing waiting. Reports from the app and the website appear here." : "Nothing reviewed yet."}</p>
        </Card>
      ) : (
        <Card className="p-0 sm:p-0">
          <Table head={["Case", "Why", "Machine said", tab === "pending" ? "Waiting" : "Label", ""]}>
            {rows.map((r) => (
              <tr key={r.item_id}>
                <td className="max-w-[340px]">
                  <div className="line-clamp-2 text-ink">{r.title || <span className="text-ink3">No claim text stored</span>}</div>
                  <div className="mt-0.5 text-xs text-ink3">
                    {kinds[r.input_type] ?? r.input_type} · checked {when(r.checked_at, true)}
                    {r.case_status !== "complete" && ` · ${r.case_status}`}
                  </div>
                </td>
                <td>
                  <Badge tone={r.reason === "user_reported" ? "bad" : "warn"}>{reasons[r.reason] ?? r.reason}</Badge>
                  {r.open_reports > 1 && <div className="mt-1 text-xs text-ink3">{r.open_reports} open on this case</div>}
                </td>
                <td className="text-ink2">{r.overall_action ? (actions[r.overall_action] ?? r.overall_action) : (r.machine_status ?? "—")}</td>
                <td className="whitespace-nowrap text-ink2">
                  {tab === "pending" ? (
                    ago(r.created_at)
                  ) : (
                    <>
                      <span className="text-ink">{labels[r.human_label ?? ""] ?? r.human_label}</span>
                      <div className="text-xs text-ink3">
                        {r.reviewer} · {when(r.reviewed_at, true)}
                      </div>
                      {r.notes && <div className="max-w-[220px] truncate text-xs text-ink3">{r.notes}</div>}
                    </>
                  )}
                </td>
                <td className="text-right whitespace-nowrap">
                  <Link href={`/app/check?case=${r.case_id}`} target="_blank" className="mr-2 text-sm font-semibold text-acc-ink">
                    Open result
                  </Link>
                  {tab === "pending" && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        setLabelling(r);
                        setLabel("CONTRADICTED");
                        setNotes("");
                        setError(null);
                      }}
                    >
                      Review
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </Table>
        </Card>
      )}

      <Modal open={!!labelling} title="Record a review" onClose={() => setLabelling(null)}>
        {labelling && (
          <form className="space-y-4" onSubmit={record}>
            <p className="text-sm text-ink2">
              Your label is kept beside the machine&apos;s verdict, never instead of it, and signed with {me?.email}.{" "}
              <Link href={`/app/check?case=${labelling.case_id}`} target="_blank" className="text-acc-ink">
                Open the result
              </Link>{" "}
              first if you haven&apos;t.
            </p>
            <Field label="What is it, in your judgement?">
              <Select value={label} onChange={(e) => setLabel(e.target.value)}>
                {Object.entries(labels).map(([value, text]) => (
                  <option key={value} value={value}>
                    {text}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Notes (optional)" hint="Sources you used, what the machine missed.">
              <Input value={notes} maxLength={4000} onChange={(e) => setNotes(e.target.value)} />
            </Field>
            {error && <Notice tone="error">{error}</Notice>}
            <Button type="submit" busy={busy} className="w-full">
              Save review
            </Button>
          </form>
        )}
      </Modal>
    </div>
  );
}
