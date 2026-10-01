"use client";

// A check, in three steps on one page: what to check (the box alone), the check
// running (what was sent, small, and how far it has got), then the answer with a
// single "check again" box. Opened from History (?case=…) it is the answer alone.

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useAccount } from "@/components/account";
import { headlineOf, labelOf, Result, Verdict } from "@/components/result";
import { Icon } from "@/components/shell";
import { Button, Notice, Spinner } from "@/components/ui";
import { api, ApiFailure, getAccount } from "@/lib/api";
import { n } from "@/lib/format";
import { addHistory, FAILED, PENDING, removeHistory, updateHistory } from "@/lib/history";

type Accepted = { case_id: string; status?: string; claims_done?: number; claims_total?: number; elapsed_seconds?: number };

const URL_ONLY = /^https?:\/\/\S+$/i;

// The server's upload limit (FACTIFY_LIMITS max_upload_bytes), said before uploading.
const MAX_UPLOAD = 25 * 1024 * 1024;

type Shown = { kind: "text" | "link" | "image" | "pdf" | "video"; submitted: string | null; preview: string | null; name?: string };

const EXAMPLES = [
  "Govt to pay ₹5,000 a month to every woman from 1 July",
  "RBI keeps repo rate unchanged in September review",
  "https://www.pib.gov.in/",
];

// As the server tells a video (`_is_video`): by its type, else by its name.
const VIDEO_NAME = /\.(mp4|mov|m4v|webm|mkv|3gp|avi)$/i;

function fileKind(file: File): "image" | "pdf" | "video" {
  if (file.type === "application/pdf" || /\.pdf$/i.test(file.name)) return "pdf";
  if (file.type.startsWith("video/") || VIDEO_NAME.test(file.name)) return "video";
  return "image";
}

const kindWord = { text: "Message", link: "Link", image: "Picture", pdf: "PDF", video: "Video" } as const;

const SHOWN_KINDS = ["text", "link", "image", "pdf", "video"] as const;

/** What was sent, kept small while it is checked. */
function Sent({ shown, onCancel }: { shown: Shown | null; onCancel?: () => void }) {
  return (
    <div className="grid grid-cols-[34px_minmax(0,1fr)_auto] items-center gap-3 rounded-[14px] border border-line bg-sf px-3.5 py-3 shadow-card">
      <span className="flex h-8.5 w-8.5 items-center justify-center rounded-[9px] bg-hover text-ink2">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" aria-hidden="true">
          <path
            d={
              shown?.kind === "video"
                ? "M3.5 6h12v12h-12zM15.5 10.5l5-3v9l-5-3"
                : shown?.kind === "image" || shown?.kind === "pdf"
                  ? "M4 4.5h16v15H4zM6 17l4-3.5 3 2.5 2.5-2 3 3"
                  : "M5 7h14M5 12h14M5 17h9"
            }
          />
        </svg>
      </span>
      <span className="min-w-0">
        <span className="line-clamp-2 block text-sm leading-relaxed text-ink">{shown?.submitted || shown?.name || "Your file"}</span>
        <span className="block text-xs text-ink3">{shown ? kindWord[shown.kind] : "Check"}</span>
      </span>
      {onCancel && (
        <Button variant="outline" size="sm" type="button" onClick={onCancel}>
          Stop
        </Button>
      )}
    </div>
  );
}

/** How far a running check has got, from what the server reports. */
function Progress({ progress, started }: { progress: Accepted | null; started: number }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  const total = progress?.claims_total ?? 0;
  const done = progress?.claims_done ?? 0;
  const steps = [
    { label: "Read what you sent", state: progress ? "done" : "now" },
    { label: total ? `Found ${n(total)} ${total === 1 ? "claim" : "claims"}` : "Finding the claims in it", state: total ? "done" : progress ? "now" : "wait" },
    {
      label: total ? `Checking each claim against trusted sources · ${n(done)} of ${n(total)}` : "Checking each claim against trusted sources",
      state: total && done >= total ? "done" : total ? "now" : "wait",
    },
    { label: "Deciding", state: total && done >= total ? "now" : "wait" },
  ];
  const seconds = progress?.elapsed_seconds ?? Math.max(0, Math.round((now - started) / 1000));
  return (
    <section className="rounded-[14px] border border-line bg-sf p-5 shadow-card" aria-live="polite">
      <div className="flex items-center justify-between">
        <h2 className="text-[15px] font-medium text-ink">Checking</h2>
        <span className="tabular font-mono text-xs text-ink3">{seconds} s</span>
      </div>
      <ol className="mt-3.5 flex flex-col gap-2.5">
        {steps.map((s) => (
          <li key={s.label} className={`flex items-center gap-3 text-sm ${s.state === "wait" ? "text-ink3" : "text-ink"}`}>
            {s.state === "done" ? (
              <svg width="18" height="18" viewBox="0 0 16 16" fill="none" className="shrink-0 text-acc-ink" aria-hidden="true">
                <circle cx="8" cy="8" r="7" fill="currentColor" fillOpacity=".15" />
                <path d="M5 8.2l2 2 4-4.2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            ) : s.state === "now" ? (
              <Spinner className="h-[18px] w-[18px] shrink-0 text-acc-ink" />
            ) : (
              <span className="flex h-[18px] w-[18px] shrink-0 items-center justify-center" aria-hidden="true">
                <span className="h-1.5 w-1.5 rounded-full bg-line2" />
              </span>
            )}
            <span>{s.label}</span>
            <span className="sr-only">{s.state === "done" ? "(done)" : s.state === "now" ? "(in progress)" : ""}</span>
          </li>
        ))}
      </ol>
      <p className="mt-4 text-xs text-ink3">Usually 20–60 seconds; a video takes a few minutes. You can leave this page: it&apos;ll be in History.</p>
    </section>
  );
}

function CheckPage() {
  const { me, current, refresh } = useAccount();
  const params = useSearchParams();
  const router = useRouter();
  const opened = params.get("case");
  const [tab, setTab] = useState<"text" | "file">("text");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<Accepted | null>(null);
  const [result, setResult] = useState<Verdict | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [started, setStarted] = useState(0);
  // What was checked, so the answer can quote it as the app does.
  const [shown, setShown] = useState<Shown | null>(null);
  const stop = useRef(false);
  // The check running now, by the id the server accepted it under: what Stop stops.
  const running = useRef<string | null>(null);

  const follow = useCallback(async (caseId: string) => {
    stop.current = false;
    for (let i = 0; i < 400 && !stop.current; i++) {
      const answer = await api<Verdict | Accepted>(`/v1/cases/${caseId}`);
      if ((answer as Verdict).verdict) return answer as Verdict;
      setProgress(answer as Accepted);
      await new Promise((r) => setTimeout(r, 2000));
    }
    if (stop.current) throw new Error("stopped");
    throw new Error("This check is taking unusually long. Look for it in History later.");
  }, []);

  const reset = useCallback(() => {
    stop.current = true;
    setBusy(false);
    setResult(null);
    setProgress(null);
    setError(null);
    setShown(null);
  }, []);

  // "New check" in the sidebar: back to the empty box.
  useEffect(() => {
    if (params.get("new")) {
      reset();
      setText("");
      setFile(null);
      router.replace("/app/check");
    }
  }, [params, reset, router]);

  // Opened from History: follow that case, nothing else.
  useEffect(() => {
    if (!opened) return;
    const k = SHOWN_KINDS.find((kind) => kind === params.get("kind"));
    setShown(k ? { kind: k, submitted: null, preview: null } : null);
    setResult(null);
    setError(null);
    setBusy(true);
    setStarted(Date.now());
    follow(opened)
      .then((answer) => {
        setResult(answer);
        // One left running in History: its verdict, now that it has one.
        const title = headlineOf(answer);
        updateHistory(opened, { case_id: answer.case_id, verdict: labelOf(answer), ...(title ? { title } : {}) });
      })
      .catch((e: Error) => {
        if (e.message === "stopped") return;
        if (e instanceof ApiFailure) updateHistory(opened, { verdict: FAILED });
        setError(e.message);
      })
      .finally(() => setBusy(false));
    return () => {
      stop.current = true;
    };
  }, [opened, params, follow]);

  /** Stop the check on the server, so it is never charged; then it leaves History. */
  async function cancel(caseId: string) {
    try {
      await api(`/v1/cases/${caseId}`, { method: "DELETE" });
      removeHistory(caseId);
    } catch (failure) {
      // 409: it had already finished, and stays in History to collect its answer.
      // 404 or 410: it is not running (any more), so there is nothing to keep.
      if (failure instanceof ApiFailure && failure.status !== 409) removeHistory(caseId);
    }
  }

  function stopCheck() {
    const caseId = running.current;
    running.current = null;
    if (caseId) cancel(caseId).catch(() => undefined);
    reset();
  }

  async function run(e?: React.FormEvent) {
    e?.preventDefault();
    setError(null);
    setResult(null);
    setProgress(null);
    const input = text.trim();
    const kind = tab === "file" ? "file" : URL_ONLY.test(input) ? "link" : "text";
    if (tab === "file" && !file) return setError("Choose a picture, PDF or video first.");
    if (tab === "file" && file && file.size > MAX_UPLOAD) return setError("That file is over 25 MB. Choose a smaller one.");
    if (tab === "text" && !input) return setError("Paste a message, a claim or a link first.");
    if (shown?.preview) URL.revokeObjectURL(shown.preview);
    setShown(
      tab === "file" && file
        ? { kind: fileKind(file), submitted: null, preview: file.type.startsWith("image/") ? URL.createObjectURL(file) : null, name: file.name }
        : { kind: kind === "link" ? "link" : "text", submitted: input, preview: null },
    );
    setBusy(true);
    setStarted(Date.now());
    stop.current = false;
    running.current = null;
    const fallbackTitle = kind === "file" ? file?.name || "File" : input.slice(0, 140);
    const historyKind = kind === "file" && file ? fileKind(file) : kind;
    try {
      let accepted: Accepted;
      if (tab === "file" && file) {
        const form = new FormData();
        form.append("file", file);
        form.append("consent_to_process_media", "true");
        form.append("background", "true");
        accepted = await api<Accepted>("/v1/verify/file", { method: "POST", body: form });
      } else {
        accepted = await api<Accepted>("/v1/verify", {
          method: "POST",
          json: { ...(kind === "link" ? { url: input } : { text: input }), mode: "background" },
        });
      }
      const at = new Date().toISOString();
      const answeredAtOnce = !!(accepted as unknown as Verdict).verdict;
      let answer: Verdict;
      if (answeredAtOnce) {
        answer = accepted as unknown as Verdict;
      } else {
        // In History from the moment it is accepted, so leaving this page leaves it
        // there; History fills in the verdict if it arrives while nobody is here.
        running.current = accepted.case_id;
        addHistory({ case_id: accepted.case_id, title: fallbackTitle, verdict: PENDING, kind: historyKind, at, account: getAccount() });
        if (stop.current) {
          // Stop was pressed before the server had accepted it.
          running.current = null;
          await cancel(accepted.case_id);
          return;
        }
        setProgress(accepted);
        answer = await follow(accepted.case_id);
      }
      running.current = null;
      setResult(answer);
      const entry = {
        // The claim it is about - never a picture's own "published before?" question.
        title: headlineOf(answer) || fallbackTitle,
        verdict: labelOf(answer),
      };
      if (answeredAtOnce) {
        addHistory({ case_id: answer.case_id, kind: historyKind, at, account: getAccount(), ...entry });
      } else {
        // A repeat served from the cache answers under the case it was first recorded as.
        updateHistory(accepted.case_id, { case_id: answer.case_id, ...entry });
      }
      refresh().catch(() => undefined);
    } catch (failure) {
      if ((failure as Error).message === "stopped") return;
      // It ended without an answer, and cost nothing: nothing to reopen. One that is
      // only taking long stays in History, still running.
      if (failure instanceof ApiFailure && running.current) removeHistory(running.current);
      running.current = null;
      if (failure instanceof ApiFailure && failure.status === 402) {
        setError(
          current
            ? `${failure.message}. ${current.role === "owner" ? "Add checks under Plan & billing, or raise the limit." : "Ask an owner of " + current.name + " for more."}`
            : `${failure.message}. Upgrade your plan or turn on extra usage under Plan & usage.`,
        );
      } else {
        setError((failure as Error).message);
      }
    } finally {
      setBusy(false);
    }
  }

  // While plan limits are not enforced (the preview), none left does not stop a check.
  const left = current
    ? current.pay_per_check
      ? `${current.name} pays per check`
      : `${n(current.checks_left)} checks left in ${current.name} this month`
    : me && !me.credits.limited && me.credits.balance <= 0
      ? "No checks left this month · you can keep checking during the preview"
      : `${n(me?.credits.balance)} checks left this month`;

  // ---- opened from History: the answer alone ----
  if (opened) {
    return (
      <div className="mx-auto flex max-w-[860px] flex-col gap-4">
        <Link href="/app/history" className="inline-flex items-center gap-1.5 self-start text-sm text-ink2 hover:text-ink">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M10 3.5L5.5 8l4.5 4.5" />
          </svg>
          History
        </Link>
        {error && <Notice tone="error">{error}</Notice>}
        {busy && !result && <Progress progress={progress} started={started} />}
        {result && <Result result={result} kind={shown?.kind} submitted={shown?.submitted} preview={shown?.preview} />}
      </div>
    );
  }

  // ---- running, then the answer ----
  if (busy || result) {
    return (
      <div className="mx-auto flex max-w-[860px] flex-col gap-4">
        {busy && (
          <>
            <Sent shown={shown} onCancel={stopCheck} />
            <Progress progress={progress} started={started} />
          </>
        )}
        {result && (
          <>
            <Result result={result} kind={shown?.kind} submitted={shown?.submitted} preview={shown?.preview} />
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-[14px] border border-dashed border-line2 px-4.5 py-4">
              <span className="text-sm text-ink2">Got another forward?</span>
              <span className="flex gap-2">
                {shown?.submitted && (
                  <Button variant="outline" type="button" onClick={() => run()}>
                    Check again
                  </Button>
                )}
                <Button
                  type="button"
                  onClick={() => {
                    reset();
                    setText("");
                    setFile(null);
                  }}
                >
                  <Icon name="plus" size={15} /> New check
                </Button>
              </span>
            </div>
          </>
        )}
      </div>
    );
  }

  // ---- what to check: the box alone ----
  return (
    <div className="mx-auto mt-4 flex max-w-[760px] flex-col gap-5 sm:mt-10">
      <div>
        <h1 className="text-[1.75rem] leading-tight font-medium tracking-tight text-ink sm:text-[2rem]">What would you like to check?</h1>
        <p className="mt-1.5 text-[15px] text-ink2">Paste a forward or a link, or upload a picture, PDF or video. A video uses 3 checks; anything else, 1.</p>
      </div>

      <form
        onSubmit={run}
        className="rounded-[14px] border border-line2 bg-sf p-3 shadow-card transition-shadow focus-within:border-acc-ink/50 focus-within:ring-4 focus-within:ring-acc-ink/10 sm:px-4 sm:pb-4"
      >
        <div role="tablist" className="mb-2.5 inline-flex gap-0.5 rounded-[9px] border border-line p-[3px]">
          {(
            [
              ["text", "Text or link"],
              ["file", "Picture, PDF or video"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={tab === id}
              onClick={() => setTab(id)}
              className={`rounded-[7px] px-3 py-1.5 text-[13px] transition-colors ${tab === id ? "bg-hover text-ink" : "text-ink2 hover:text-ink"}`}
            >
              {label}
            </button>
          ))}
        </div>

        {tab === "text" ? (
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) run();
            }}
            rows={6}
            maxLength={50000}
            placeholder="Paste a WhatsApp forward, a claim or a news link…"
            aria-label="What to check"
            className="block w-full resize-y bg-transparent px-1 py-1 text-[17px] leading-relaxed text-ink placeholder:text-ink3 focus:outline-none"
          />
        ) : (
          <label
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              if (e.dataTransfer.files?.[0]) setFile(e.dataTransfer.files[0]);
            }}
            className="flex min-h-40 cursor-pointer flex-col items-center justify-center gap-2 rounded-[11px] border border-dashed border-line2 px-4 py-8 text-center transition-colors hover:bg-hover"
          >
            <input type="file" accept="image/*,application/pdf,video/*" className="sr-only" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className="text-acc-ink" aria-hidden="true">
              <path d="M12 16V5M7.5 9.5L12 5l4.5 4.5M5 15v2.5A1.5 1.5 0 006.5 19h11a1.5 1.5 0 001.5-1.5V15" />
            </svg>
            <span className="text-[15px] text-ink">
              {file ? (
                file.name
              ) : (
                <>
                  Drop a file here, or <span className="text-acc-ink">choose one</span>
                </>
              )}
            </span>
            <span className="text-[13px] text-ink3">{file ? `${(file.size / 1024 / 1024).toFixed(1)} MB` : "Pictures, PDFs and videos up to 25 MB · videos up to 90 seconds"}</span>
          </label>
        )}

        <div className="mt-2.5 flex flex-col-reverse gap-3 border-t border-line pt-3 sm:flex-row sm:items-center sm:justify-between">
          <span className="text-[13px] text-ink3">
            Language detected automatically · <span className="text-ink2">{left}</span>
          </span>
          <Button type="submit" className="w-full sm:w-auto">
            Check now <span className="hidden rounded-[5px] bg-black/15 px-1.5 py-px font-mono text-[11px] sm:inline">Ctrl ↵</span>
          </Button>
        </div>
      </form>

      {error && <Notice tone="error">{error}</Notice>}

      <div className="flex flex-wrap items-center gap-2">
        <span className="mr-1 text-[13px] text-ink3">Try an example:</span>
        {EXAMPLES.map((example) => (
          <button
            key={example}
            type="button"
            onClick={() => {
              setTab("text");
              setText(example);
            }}
            className="max-w-full truncate rounded-lg border border-line px-3 py-1.5 text-[13px] text-ink2 transition-colors hover:border-line2 hover:bg-hover hover:text-ink"
          >
            {example}
          </button>
        ))}
      </div>
    </div>
  );
}

export default function Page() {
  return (
    <Suspense>
      <CheckPage />
    </Suspense>
  );
}
