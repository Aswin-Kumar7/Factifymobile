"use client";

// The four questions a new account is asked once, as on the phone
// (apps/mobile/lib/screens/survey_screen.dart): shown after sign-in while the server
// says the survey is due (`survey_due` on /v1/me), answered or skipped with
// PUT /v1/me/survey. The answer keys are the server's (app/accounts/credits.py).
// Every question can be passed over, the whole survey skipped, and a failure to save
// never holds anyone here: the server still has it due, so it is offered next time.

import { useState } from "react";
import { api } from "@/lib/api";
import { useAccount } from "./account";
import { Button, Modal, Notice } from "./ui";

type Question = { key: "role" | "places" | "wants" | "heard"; title: string; many: boolean; options: [string, string][] };

const QUESTIONS: Question[] = [
  {
    key: "role",
    title: "What brings you to Factify?",
    many: false,
    options: [
      ["journalist", "Journalist or fact-checker"],
      ["student", "Student or researcher"],
      ["teacher", "Teacher"],
      ["family", "Checking forwards for family and friends"],
      ["curious", "Just curious"],
    ],
  },
  {
    key: "places",
    title: "Where do you see things you'd like to check?",
    many: true,
    options: [
      ["whatsapp", "WhatsApp"],
      ["instagram", "Instagram"],
      ["youtube", "YouTube"],
      ["facebook", "Facebook"],
      ["x", "X"],
      ["telegram", "Telegram"],
      ["news_sites", "News sites"],
    ],
  },
  {
    key: "wants",
    title: "What do you want to check most?",
    many: true,
    options: [
      ["forwards", "Forwards and messages"],
      ["links", "News links"],
      ["pictures", "Pictures"],
      ["videos", "Videos"],
      ["voice", "Voice notes"],
    ],
  },
  {
    key: "heard",
    title: "How did you hear about Factify?",
    many: false,
    options: [
      ["friend", "From a friend"],
      ["social", "On social media"],
      ["college", "At college or an event"],
      ["other", "Somewhere else"],
    ],
  },
];

type Answers = { role: string | null; places: string[]; wants: string[]; heard: string | null };

export function Survey() {
  const { me, refresh } = useAccount();
  const [closed, setClosed] = useState(false);
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const [answers, setAnswers] = useState<Answers>({ role: null, places: [], wants: [], heard: null });

  if (!me?.survey_due || closed) return null;

  const q = QUESTIONS[step];
  const last = step === QUESTIONS.length - 1;

  const chosen = (value: string) => {
    const current = answers[q.key];
    return Array.isArray(current) ? current.includes(value) : current === value;
  };

  const pick = (value: string) =>
    setAnswers((a) => {
      if (q.key === "places" || q.key === "wants") {
        const list = a[q.key];
        return { ...a, [q.key]: list.includes(value) ? list.filter((v) => v !== value) : [...list, value] };
      }
      return { ...a, [q.key]: a[q.key] === value ? null : value };
    });

  async function finish(skipped: boolean) {
    setBusy(true);
    setFailed(false);
    try {
      await api("/v1/me/survey", { method: "PUT", json: skipped ? { skipped: true } : answers, account: "personal" });
      await refresh().catch(() => undefined);
      setClosed(true);
    } catch {
      setFailed(true);
      setBusy(false);
    }
  }

  return (
    <Modal open title={q.title} onClose={() => setClosed(true)}>
      <p className="-mt-2 mb-4 text-sm text-ink3">
        {step + 1} of {QUESTIONS.length} · {step === 0 ? "Four quick questions help us build Factify for you. Skip any you like." : q.many ? "Pick any that fit" : "Pick one"}
      </p>
      <div className={q.many ? "flex flex-wrap gap-2" : "flex flex-col gap-2"}>
        {q.options.map(([value, label]) => {
          const on = chosen(value);
          return (
            <button
              key={value}
              type="button"
              aria-pressed={on}
              onClick={() => pick(value)}
              className={`rounded-[10px] border px-3.5 py-2.5 text-left text-sm transition-colors ${
                on ? "border-acc-ink bg-acc-soft text-ink" : "border-line2 text-ink2 hover:bg-hover hover:text-ink"
              }`}
            >
              {label}
            </button>
          );
        })}
      </div>
      {failed && (
        <div className="mt-4">
          <Notice tone="error">Your answers couldn&apos;t be saved. You can carry on anyway; we&apos;ll ask again next time.</Notice>
        </div>
      )}
      <div className="mt-6 flex items-center justify-between gap-3">
        <Button variant="ghost" size="sm" onClick={() => finish(true)} disabled={busy}>
          Skip all
        </Button>
        <div className="flex gap-2">
          {step > 0 && (
            <Button variant="outline" size="sm" onClick={() => setStep(step - 1)} disabled={busy}>
              Back
            </Button>
          )}
          <Button size="sm" busy={busy} onClick={() => (last ? finish(false) : setStep(step + 1))}>
            {last ? "Finish" : "Next"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
