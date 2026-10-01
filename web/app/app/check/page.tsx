"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useAccount } from "@/components/account";
import { headlineOf, labelOf, Result, Verdict } from "@/components/result";
import { Button, Notice, PageTitle, Spinner } from "@/components/ui";
import { api, ApiFailure, getAccount } from "@/lib/api";
import { addHistory } from "@/lib/history";
import { n } from "@/lib/format";

type Accepted = { case_id: string; status?: string; claims_done?: number; claims_total?: number; elapsed_seconds?: number };

const URL_ONLY = /^https?:\/\/\S+$/i;

// The server's upload limit (FACTIFY_LIMITS max_upload_bytes), said before uploading.
const MAX_UPLOAD = 25 * 1024 * 1024;

type Shown = { kind: "text" | "link" | "image" | "pdf"; submitted: string | null; preview: string | null };

function fileKind(file: File): "image" | "pdf" {
  return file.type === "application/pdf" || /\.pdf$/i.test(file.name) ? "pdf" : "image";
}

function CheckPage() {
  const { me, current, refresh } = useAccount();
  const params = useSearchParams();
  const [tab, setTab] = useState<"text" | "file">("text");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<Accepted | null>(null);
  const [result, setResult] = useState<Verdict | null>(null);
  const [error, setError] = useState<string | null>(null);
  // What was checked, so the answer can quote it as the app does.
  const [shown, setShown] = useState<Shown | null>(null);
  const stop = useRef(false);

  const follow = useCallback(async (caseId: string) => {
    stop.current = false;
    for (let i = 0; i < 400 && !stop.current; i++) {
      const answer = await api<Verdict | Accepted>(`/v1/cases/${caseId}`);
      if ((answer as Verdict).verdict) return answer as Verdict;
      setProgress(answer as Accepted);
      await new Promise((r) => setTimeout(r, 2000));
    }
    throw new Error("This check is taking unusually long. Look for it in History later.");
  }, []);

  useEffect(() => {
    const caseId = params.get("case");
    if (!caseId) return;
    const k = params.get("kind");
    setShown(k === "text" || k === "link" || k === "image" || k === "pdf" ? { kind: k, submitted: null, preview: null } : null);
    setBusy(true);
    follow(caseId)
      .then(setResult)
      .catch((e: Error) => setError(e.message))
      .finally(() => setBusy(false));
    return () => {
      stop.current = true;
    };
  }, [params, follow]);

  async function run(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setResult(null);
    setProgress(null);
    setBusy(true);
    const input = text.trim();
    const kind = tab === "file" ? "file" : URL_ONLY.test(input) ? "link" : "text";
    if (shown?.preview) URL.revokeObjectURL(shown.preview);
    setShown(
      tab === "file"
        ? file
          ? { kind: fileKind(file), submitted: null, preview: file.type.startsWith("image/") ? URL.createObjectURL(file) : null }
          : null
        : { kind: kind === "link" ? "link" : "text", submitted: input, preview: null },
    );
    try {
      let accepted: Accepted;
      if (tab === "file") {
        if (!file) throw new Error("Choose a picture, PDF or video first.");
        if (file.size > MAX_UPLOAD) throw new Error("That file is over 25 MB. Choose a smaller one.");
        const form = new FormData();
        form.append("file", file);
        form.append("consent_to_process_media", "true");
        form.append("background", "true");
        accepted = await api<Accepted>("/v1/verify/file", { method: "POST", body: form });
      } else {
        if (!input) throw new Error("Paste a message, a claim or a link first.");
        accepted = await api<Accepted>("/v1/verify", {
          method: "POST",
          json: { ...(kind === "link" ? { url: input } : { text: input }), mode: "background" },
        });
      }
      setProgress(accepted);
      const answer = (accepted as unknown as Verdict).verdict ? (accepted as unknown as Verdict) : await follow(accepted.case_id);
      setResult(answer);
      addHistory({
        case_id: answer.case_id,
        // The claim it is about - never a picture's own "published before?" question.
        title: headlineOf(answer) || (kind === "file" ? file?.name || "File" : input.slice(0, 140)),
        verdict: labelOf(answer),
        kind: kind === "file" && file ? fileKind(file) : kind,
        at: new Date().toISOString(),
        account: getAccount(),
      });
      refresh().catch(() => undefined);
    } catch (failure) {
      if (failure instanceof ApiFailure && failure.status === 402) {
        setError(
          current
            ? `${failure.message}. ${current.role === "owner" ? "Buy credits under Billing, or raise the limit." : "Ask an owner of " + current.name + " for more credits."}`
            : failure.message,
        );
      } else {
        setError((failure as Error).message);
      }
    } finally {
      setBusy(false);
    }
  }

  const paying = current ? `${current.name}'s credits (${n(current.balance)} left)` : `your free credits (${n(me?.credits.balance)} left)`;

  return (
    <>
      <PageTitle eyebrow={current ? current.name : "Workspace"} title="What would you like to check?" sub={<>Paid from {paying}. A video uses 3 credits; anything else, 1.</>} />

      <form onSubmit={run} className="paper rounded-3xl border border-line bg-sf p-3 shadow-lift sm:p-5">
        <div role="tablist" className="mb-3 inline-flex w-full rounded-xl bg-sf2 p-1 sm:w-auto">
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
              className={`flex-1 rounded-lg px-3 py-2 text-sm font-semibold sm:flex-none sm:px-4 ${tab === id ? "bg-sf text-ink shadow-sm" : "text-ink2"}`}
            >
              {label}
            </button>
          ))}
        </div>

        {tab === "text" ? (
          <>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={6}
            maxLength={50000}
            placeholder="Paste a message, a claim or a news link"
            aria-label="What to check"
            className="block w-full resize-y rounded-xl bg-transparent px-2 py-2 font-serif text-[1.35rem] leading-snug text-ink placeholder:text-ink3 focus:outline-none sm:text-2xl"
          />
          {!text && (
            <div className="flex flex-wrap gap-2 px-1 pb-1">
              {[
                "Govt to pay ₹5,000 a month to every woman from 1 July",
                "RBI keeps repo rate unchanged in September review",
                "https://www.pib.gov.in/",
              ].map((example) => (
                <button
                  key={example}
                  type="button"
                  onClick={() => setText(example)}
                  className="max-w-full truncate rounded-full border border-line bg-bg px-3 py-1.5 text-xs text-ink2 hover:border-acc hover:text-ink"
                >
                  Try: {example}
                </button>
              ))}
            </div>
          )}
          </>
        ) : (
          <label className="flex min-h-40 cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-line px-4 py-8 text-center hover:bg-sf2">
            <input
              type="file"
              accept="image/*,application/pdf,video/*"
              className="sr-only"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
            <span className="font-semibold text-ink">{file ? file.name : "Choose a file"}</span>
            <span className="text-sm text-ink3">
              {file ? `${(file.size / 1024 / 1024).toFixed(1)} MB` : "Pictures, PDFs and videos up to 25 MB"}
            </span>
          </label>
        )}

        <div className="mt-3 flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between">
          <span className="text-xs text-ink3">Usually 20-60 seconds; a video takes a few minutes.</span>
          <Button type="submit" busy={busy} size="lg" className="w-full sm:w-auto">
            Check now
          </Button>
        </div>
      </form>

      <div className="mt-6 space-y-4" aria-live="polite">
        {error && <Notice tone="error">{error}</Notice>}
        {busy && !result && (
          <div className="flex items-center gap-3 rounded-2xl border border-line bg-sf p-4 text-ink2">
            <Spinner className="text-acc" />
            <span>
              {progress?.claims_total
                ? `Checking: ${progress.claims_done ?? 0} of ${progress.claims_total} claims done`
                : "Reading it and finding sources…"}
            </span>
          </div>
        )}
        {result && <Result result={result} kind={shown?.kind} submitted={shown?.submitted} preview={shown?.preview} />}
      </div>
    </>
  );
}

export default function Page() {
  return (
    <Suspense>
      <CheckPage />
    </Suspense>
  );
}
