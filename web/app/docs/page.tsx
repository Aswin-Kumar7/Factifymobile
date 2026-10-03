import type { Metadata } from "next";
import Link from "next/link";
import { CodeTabs, CopyButton } from "@/components/docs";
import { SiteFooter, SiteHeader } from "@/components/site";

export const metadata: Metadata = { title: "API docs" };

const BASE = "https://factify-zeai.indiasouthcentral.cloudapp.azure.com";

// ---- small pieces ------------------------------------------------------------------

type Method = "GET" | "POST" | "DELETE";

const METHOD: Record<Method, string> = {
  GET: "bg-[var(--chart-4)]/15 text-[var(--chart-4)]",
  POST: "bg-acc-soft text-acc-ink",
  DELETE: "bg-false-soft text-false",
};

function Endpoint({ method, path }: { method: Method; path: string }) {
  return (
    <div className="inline-flex max-w-full items-center gap-2.5 rounded-xl border border-line bg-sf px-3 py-2 font-mono text-[13px]">
      <span className={`rounded-md px-2 py-0.5 text-[11.5px] font-semibold ${METHOD[method]}`}>{method}</span>
      <span className="truncate text-ink">{path}</span>
    </div>
  );
}

function Section({ id, eyebrow, title, children }: { id: string; eyebrow?: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} className="scroll-mt-28 border-t border-line pt-14 pb-4 first:border-t-0 first:pt-0">
      {eyebrow && <span className="eyebrow">{eyebrow}</span>}
      <h2 className="mt-2 text-[1.75rem] font-medium tracking-tight text-ink">{title}</h2>
      <div className="mt-4">{children}</div>
    </section>
  );
}

/** Explanation on the left, code on the right, on wide screens. */
function Split({ children, code }: { children: React.ReactNode; code: React.ReactNode }) {
  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)] xl:gap-7">
      <div className="flex min-w-0 flex-col gap-4 text-[15px] leading-relaxed text-ink2">{children}</div>
      <div className="min-w-0 xl:sticky xl:top-28 xl:self-start">{code}</div>
    </div>
  );
}

function C({ children }: { children: React.ReactNode }) {
  return <code className="rounded-md bg-sf2 px-1.5 py-0.5 font-mono text-[0.88em] text-ink">{children}</code>;
}

function Fields({ rows, heads = ["Field", "Type", "Description"] }: { rows: [string, string, React.ReactNode][]; heads?: string[] }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-line">
      <table className="w-full min-w-[400px] text-left text-[14px]">
        <thead className="bg-sf2/70 text-[12px] tracking-wide text-ink3 uppercase">
          <tr>
            {heads.map((h) => (
              <th key={h} className="px-3.5 py-2.5 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(([a, b, c], i) => (
            <tr key={`${i}-${a}-${b}`} className="border-t border-line align-top">
              <td className="px-3.5 py-3 font-mono text-[13px] whitespace-nowrap text-ink">{a}</td>
              <td className="px-3.5 py-3 font-mono text-[12px] whitespace-nowrap text-ink3">{b}</td>
              <td className="px-3.5 py-3 text-ink2">{c}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Callout({ children }: { children: React.ReactNode }) {
  return <div className="rounded-xl border border-acc-ink/25 bg-acc-soft px-4 py-3 text-[14px] leading-relaxed text-ink2">{children}</div>;
}

// ---- content -----------------------------------------------------------------------

const NAV: [string, [string, string][]][] = [
  ["Getting started", [["overview", "Overview"], ["auth", "Authentication"], ["quickstart", "Quickstart"]]],
  [
    "Endpoints",
    [
      ["verify", "Check text or a link"],
      ["verify-file", "Check a picture, PDF or video"],
      ["cases", "Get a case"],
      ["stop", "Stop a check"],
      ["events", "Live progress"],
      ["evidence", "Every citation"],
      ["correction", "Correction message"],
      ["receipts", "Receipts"],
    ],
  ],
  ["Reference", [["answer", "The answer"], ["credits", "Credits"], ["errors", "Errors"], ["limits", "Rate limits & retries"], ["safety", "Keeping keys safe"]]],
];

const VERDICTS: [string, string, string][] = [
  ["TRUE", "text-true bg-true-soft", "Two or more independent trusted sources confirm it."],
  ["FALSE", "text-false bg-false-soft", "A fact-check, a highly credible source or two independent sources contradict it."],
  ["PARTLY_TRUE", "text-mis bg-mis-soft", "Only a smaller version is true, or one part is wrong."],
  ["MISLEADING", "text-mis bg-mis-soft", "Real material shown out of context, or framed to mislead."],
  ["UNCONFIRMED", "text-unc bg-unc-soft", "Not enough evidence to decide. Never a guess."],
];

const RESPONSE = `{
  "case_id": "3b6f0c1e-…",
  "verdict": "FALSE",
  "confidence": 89,
  "summary": "PIB Fact Check has fact-checked this and found it false: …",
  "action": "DO_NOT_SHARE",
  "claims": [
    {
      "id": "cl_1",
      "text": "Applications are open for the National Sports Scholarship 2026-27.",
      "status": "CONTRADICTED",
      "explanation": "PIB Fact Check: “This scholarship scheme is fake …”",
      "evidence": [
        {
          "publisher": "PIB Fact Check",
          "citation_url": "https://pib.gov.in/…",
          "source_excerpt": "This scholarship scheme is fake …",
          "direction": "contradicts"
        }
      ]
    }
  ],
  "input_read": { "complete": true, "parts": [ … ], "gaps": [] },
  "skipped": [],
  "receipt_url": "${BASE}/v1/receipts/…"
}`;

export default function Docs() {
  return (
    <>
      <SiteHeader />
      <main>
        {/* Hero */}
        <section className="relative isolate overflow-hidden border-b border-line">
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(var(--grid)_1px,transparent_1.3px)] bg-[size:22px_22px] [mask-image:radial-gradient(ellipse_70%_70%_at_20%_30%,black,transparent)]"
          />
          <div aria-hidden="true" className="pointer-events-none absolute -top-40 -left-20 -z-10 h-[460px] w-[680px] rounded-full bg-[radial-gradient(closest-side,var(--glow),transparent)] opacity-60 blur-2xl" />
          <div className="mx-auto grid max-w-[1200px] gap-10 px-4 pt-16 pb-14 sm:px-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,.9fr)] lg:items-end">
            <div className="flex flex-col gap-5">
              <span className="eyebrow">Developers</span>
              <h1 className="text-[2.6rem] leading-[1.04] font-medium tracking-[-0.04em] text-ink sm:text-[3.4rem]">
                The Factify <span className="text-acc-ink">API</span>
              </h1>
              <p className="max-w-[560px] text-[17px] leading-relaxed text-ink2">
                Check text, links, posts, pictures, PDFs and videos from your own product. Every answer comes with the claims found, the trusted sources read and the exact
                sentence that decided it &mdash; the same answer as the app.
              </p>
              <div className="flex flex-wrap gap-3">
                <Link href={`/signup?next=${encodeURIComponent("/app/org/new")}`} className="inline-flex h-11 items-center gap-2 rounded-[10px] bg-acc px-5 text-[15px] font-medium text-on-acc hover:bg-acc-h">
                  Get an API key
                </Link>
                <a href={`${BASE}/openapi.json`} className="inline-flex h-11 items-center gap-2 rounded-[10px] border border-line2 px-5 text-[15px] font-medium text-ink hover:bg-hover">
                  OpenAPI spec
                </a>
              </div>
            </div>
            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between gap-3 rounded-2xl border border-white/10 bg-[#0b100d] px-4 py-3">
                <span className="min-w-0">
                  <span className="block text-[11px] tracking-wide text-[#76847c] uppercase">Base URL</span>
                  <span className="block truncate font-mono text-[13px] text-[#dfe9e3]">{BASE}</span>
                </span>
                <CopyButton value={BASE} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                {[
                  ["REST + JSON", "One JSON answer per check"],
                  ["Bearer keys", "fct_live_… per organisation"],
                  ["60 / minute", "per key, 300 per organisation"],
                  ["12 languages", "English and Indian languages"],
                ].map(([a, b]) => (
                  <div key={a} className="rounded-2xl border border-line bg-sf p-4 shadow-card">
                    <div className="text-[15px] font-medium text-ink">{a}</div>
                    <div className="mt-0.5 text-[13px] text-ink3">{b}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        <div className="mx-auto grid max-w-[1200px] gap-10 px-4 py-14 sm:px-8 lg:grid-cols-[210px_minmax(0,1fr)] lg:gap-14">
          {/* Sidebar */}
          <nav aria-label="API docs" className="hidden lg:block">
            <div className="sticky top-28 flex flex-col gap-6">
              {NAV.map(([group, items]) => (
                <div key={group} className="flex flex-col gap-1">
                  <span className="mb-1 text-[11.5px] font-medium tracking-wide text-ink3 uppercase">{group}</span>
                  {items.map(([id, label]) => (
                    <a key={id} href={`#${id}`} className="rounded-lg px-2.5 py-1.5 text-[14px] text-ink2 transition-colors hover:bg-hover hover:text-ink">
                      {label}
                    </a>
                  ))}
                </div>
              ))}
            </div>
          </nav>

          <div className="flex min-w-0 flex-col gap-2">
            <Section id="overview" eyebrow="Getting started" title="Overview">
              <div className="grid gap-3 sm:grid-cols-3">
                {[
                  ["1", "Create a key", "In the dashboard, under API keys. Keys belong to an organisation; checks are paid from its credit pool."],
                  ["2", "Send a check", "POST text or a link to /v1/verify, or a file to /v1/verify/file."],
                  ["3", "Read the answer", "A verdict, its confidence, each claim and the sources that decided it."],
                ].map(([n, h, b]) => (
                  <div key={n} className="rounded-2xl border border-line bg-sf p-5 shadow-card">
                    <span className="flex h-7 w-7 items-center justify-center rounded-full bg-acc text-[13px] font-semibold text-on-acc">{n}</span>
                    <div className="mt-3 text-[15.5px] font-medium text-ink">{h}</div>
                    <p className="mt-1 text-[14px] leading-relaxed text-ink2">{b}</p>
                  </div>
                ))}
              </div>
            </Section>

            <Section id="auth" title="Authentication">
              <Split code={<CodeTabs samples={[{ lang: "Header", code: "Authorization: Bearer fct_live_…" }]} />}>
                <p>
                  Send your key as a bearer token on every request. Keys start with <C>fct_live_</C> and are shown only once, when they are created.
                </p>
                <p>A key can carry a monthly limit, an expiry date and an IP allowlist, all set in the dashboard.</p>
              </Split>
            </Section>

            <Section id="quickstart" title="Quickstart">
              <Split
                code={
                  <CodeTabs
                    title="POST /v1/verify"
                    samples={[
                      {
                        lang: "cURL",
                        code: `curl ${BASE}/v1/verify \\
  -H "Authorization: Bearer $FACTIFY_KEY" \\
  -H "Content-Type: application/json" \\
  -H "Idempotency-Key: $(uuidgen)" \\
  -d '{"text": "Govt to pay ₹5,000 a month to every woman from 1 July."}'`,
                      },
                      {
                        lang: "Python",
                        code: `import os, requests

r = requests.post(
    "${BASE}/v1/verify",
    headers={"Authorization": f"Bearer {os.environ['FACTIFY_KEY']}"},
    json={"url": "https://example.com/viral-story"},
    timeout=120,
)
r.raise_for_status()
answer = r.json()
print(answer["verdict"], answer["summary"])
for claim in answer["claims"]:
    print("-", claim["text"], claim["status"])
    for source in claim["evidence"]:
        print("   ", source["direction"], source["citation_url"])`,
                      },
                      {
                        lang: "JavaScript",
                        code: `const r = await fetch("${BASE}/v1/verify", {
  method: "POST",
  headers: {
    Authorization: \`Bearer \${process.env.FACTIFY_KEY}\`,
    "Content-Type": "application/json",
  },
  body: JSON.stringify({ text: "RBI keeps repo rate unchanged" }),
});
const answer = await r.json();
console.log(answer.verdict, r.headers.get("Factify-Credits-Remaining"));`,
                      },
                    ]}
                  />
                }
              >
                <p>Your first check, in one request. Keep the key on your server and read it from an environment variable.</p>
                <Callout>
                  A check usually takes 20&ndash;60 seconds. An answer already known comes back in about 3 seconds. For long inputs, use{" "}
                  <C>&quot;mode&quot;: &quot;background&quot;</C> and poll the case.
                </Callout>
              </Split>
            </Section>

            <Section id="verify" eyebrow="Endpoints" title="Check text or a link">
              <Split
                code={
                  <CodeTabs
                    title="Response · 200"
                    samples={[
                      { lang: "JSON", code: RESPONSE },
                      {
                        lang: "Background · 202",
                        code: `{\n  "case_id": "3b6f0c1e-…",\n  "status": "processing",\n  "poll_url": "/v1/cases/3b6f0c1e-…",\n  "estimated_seconds": 30\n}\n\n# then poll poll_url: 202 while running, 200 with the answer`,
                      },
                    ]}
                  />
                }
              >
                <Endpoint method="POST" path="/v1/verify" />
                <p>
                  Send exactly one of <C>text</C> or <C>url</C>. A link to an article is read in full; a link to an X or Instagram post is read with its text, pictures and
                  video; a YouTube link with its title, description and captions.
                </p>
                <Fields
                  rows={[
                    ["text", "string", "The message to check, up to 50,000 characters."],
                    ["url", "string", "A link to an article or a post."],
                    [
                      "mode",
                      "string",
                      <>
                        <C>fast</C> (default) answers in this request; <C>background</C> answers <C>202</C> with a <C>case_id</C> at once.
                      </>,
                    ],
                    ["recheck", "boolean", "Skip the stored answer and check from scratch."],
                    ["accept_partial", "boolean", "Check what could be read of a post or page, even if part of it could not be."],
                  ]}
                />
              </Split>
            </Section>

            <Section id="verify-file" title="Check a picture, PDF or video">
              <Split
                code={
                  <CodeTabs
                    title="POST /v1/verify/file"
                    samples={[
                      {
                        lang: "cURL",
                        code: `curl ${BASE}/v1/verify/file \\
  -H "Authorization: Bearer $FACTIFY_KEY" \\
  -F file=@photo.jpg \\
  -F consent_to_process_media=true`,
                      },
                      {
                        lang: "Python",
                        code: `with open("photo.jpg", "rb") as f:
    r = requests.post(
        "${BASE}/v1/verify/file",
        headers={"Authorization": f"Bearer {os.environ['FACTIFY_KEY']}"},
        files={"file": f},
        data={"consent_to_process_media": "true"},
        timeout=120,
    )`,
                      },
                    ]}
                  />
                }
              >
                <Endpoint method="POST" path="/v1/verify/file" />
                <p>
                  A multipart form with <C>file</C> and <C>consent_to_process_media=true</C>, up to 25 MB. The words in the picture or frames are read, what it shows is
                  described, speech in a video is transcribed, and the AI-image and face-swap checks run.
                </p>
                <Fields
                  rows={[
                    ["file", "file", "A picture (JPEG, PNG, WebP), a PDF or a video."],
                    ["consent_to_process_media", "boolean", "Must be true."],
                    ["background", "boolean", "Answer 202 at once and check in the background."],
                  ]}
                />
                <Callout>
                  A video always answers <C>202</C>; poll its <C>case_id</C>. Uploaded files are never stored.
                </Callout>
              </Split>
            </Section>

            <Section id="cases" title="Get a case">
              <Split code={<CodeTabs samples={[{ lang: "cURL", code: `curl ${BASE}/v1/cases/$CASE_ID \\\n  -H "Authorization: Bearer $FACTIFY_KEY"` }]} />}>
                <Endpoint method="GET" path="/v1/cases/{case_id}" />
                <p>
                  The answer of a check. While a background check is running it answers <C>202</C>; poll every few seconds until it answers <C>200</C>.
                </p>
              </Split>
            </Section>

            <Section id="stop" title="Stop a check">
              <Split code={<CodeTabs samples={[{ lang: "cURL", code: `curl -X DELETE ${BASE}/v1/cases/$CASE_ID \\\n  -H "Authorization: Bearer $FACTIFY_KEY"` }]} />}>
                <Endpoint method="DELETE" path="/v1/cases/{case_id}" />
                <p>
                  Stops a check still running in the background. Answers <C>204</C>. A stopped check costs nothing.
                </p>
              </Split>
            </Section>

            <Section id="events" title="Live progress">
              <Split
                code={
                  <CodeTabs
                    samples={[
                      {
                        lang: "JavaScript",
                        code: `const events = new EventSource("${BASE}/v1/cases/" + caseId + "/events");
events.onmessage = (e) => console.log(JSON.parse(e.data));
// ends with a "done" or "error" event`,
                      },
                    ]}
                  />
                }
              >
                <Endpoint method="GET" path="/v1/cases/{key}/events" />
                <p>
                  Server-Sent Events while a check runs: its steps, each source as it is read, the evidence count. <C>key</C> is a background check&apos;s case id. Reconnect
                  with <C>Last-Event-ID</C> to resume.
                </p>
              </Split>
            </Section>

            <Section id="evidence" title="Every citation">
              <Split code={<CodeTabs samples={[{ lang: "cURL", code: `curl ${BASE}/v1/cases/$CASE_ID/evidence \\\n  -H "Authorization: Bearer $FACTIFY_KEY"` }]} />}>
                <Endpoint method="GET" path="/v1/cases/{case_id}/evidence" />
                <p>Every source behind a case: publisher, link, the passage read and whether it supports, contradicts or only gives context.</p>
              </Split>
            </Section>

            <Section id="correction" title="Correction message">
              <Split
                code={
                  <CodeTabs
                    samples={[
                      {
                        lang: "cURL",
                        code: `curl ${BASE}/v1/cases/$CASE_ID/correction-text \\
  -H "Authorization: Bearer $FACTIFY_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"language": "hi"}'`,
                      },
                    ]}
                  />
                }
              >
                <Endpoint method="POST" path="/v1/cases/{case_id}/correction-text" />
                <p>
                  A short, polite message to send back to the chat, with its sources. <C>language</C> is one of <C>en</C>, <C>hi</C>, <C>bn</C>, <C>mr</C>, <C>te</C>,{" "}
                  <C>ta</C>, <C>gu</C>, <C>ur</C>, <C>kn</C>, <C>or</C>, <C>ml</C>, <C>pa</C>.
                </p>
              </Split>
            </Section>

            <Section id="receipts" title="Receipts">
              <Split code={<CodeTabs samples={[{ lang: "cURL", code: `curl ${BASE}/v1/receipts/$RECEIPT_ID` }]} />}>
                <Endpoint method="GET" path="/v1/receipts/{receipt_id}" />
                <p>
                  Every answer carries a <C>receipt_url</C>: a signed, tamper-evident fingerprint of the evidence behind it. Anyone can verify it later.
                </p>
              </Split>
            </Section>

            <Section id="answer" eyebrow="Reference" title="The answer">
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {VERDICTS.map(([v, tone, d]) => (
                  <div key={v} className="rounded-2xl border border-line bg-sf p-4 shadow-card">
                    <span className={`rounded-md px-2 py-0.5 font-mono text-[12px] font-semibold ${tone}`}>{v}</span>
                    <p className="mt-2.5 text-[14px] leading-relaxed text-ink2">{d}</p>
                  </div>
                ))}
              </div>
              <div className="mt-5">
                <Fields
                  rows={[
                    ["verdict", "string", "One of the five verdicts above."],
                    [
                      "confidence",
                      "integer | null",
                      <>
                        50&ndash;97, computed from the sources; <C>null</C> when nothing was decided.
                      </>,
                    ],
                    ["summary", "string | null", "One plain sentence: the explanation of the claim that decided it."],
                    [
                      "claims[]",
                      "array",
                      <>
                        Each claim&apos;s <C>text</C>, <C>status</C> (<C>SUPPORTED</C>, <C>CONTRADICTED</C>, <C>MISLEADING_CONTEXT</C>, <C>UNVERIFIED</C>) and{" "}
                        <C>evidence</C>.
                      </>,
                    ],
                    [
                      "evidence[]",
                      "array",
                      <>
                        <C>citation_url</C>, <C>publisher</C>, <C>source_excerpt</C> and <C>direction</C> (<C>supports</C>, <C>contradicts</C>, <C>contextualizes</C>).
                      </>,
                    ],
                    ["input_read", "object", "What was read from the input — post text, pictures, video, article — and what could not be."],
                    ["skipped[]", "array", "Checks that could not run, and why."],
                  ]}
                />
              </div>
              <p className="mt-4 text-[14px] text-ink3">
                The full schema is in the{" "}
                <a href={`${BASE}/openapi.json`} className="text-acc-ink underline">
                  OpenAPI spec
                </a>
                .
              </p>
            </Section>

            <Section id="credits" title="Credits">
              <Split
                code={
                  <CodeTabs
                    samples={[
                      {
                        lang: "Response headers",
                        code: `Factify-Credits-Used: 1\nFactify-Credits-Remaining: 2,349`,
                      },
                    ]}
                  />
                }
              >
                <Fields
                  heads={["Check", "Credits", ""]}
                  rows={[
                    ["Text, link, picture or PDF", "1", "The same for every plan: no plan checks less carefully."],
                    ["Video", "3", "Frames, speech and face checks."],
                    ["Answer already known", "1", "Served from the cache in about 3 seconds."],
                    ["A check that fails or is stopped", "0", "Never charged."],
                  ]}
                />
                <p>Credits are held when a check starts and charged when it answers, so parallel requests can never spend more than the pool, the member&apos;s limit or the key&apos;s limit allows.</p>
              </Split>
            </Section>

            <Section id="errors" title="Errors">
              <p className="mb-4 text-[15px] text-ink2">
                Every error has a JSON body with <C>detail</C> (for people) and <C>error_code</C> (for programs).
              </p>
              <Fields
                heads={["Status", "error_code", "Meaning"]}
                rows={[
                  ["401", "invalid_api_key", "Unknown, mistyped, revoked or expired key."],
                  ["403", "key_not_allowed", "Organisation suspended, key's creator removed, or IP not allowed."],
                  ["402", "insufficient_credits", "The pool can't pay for this check."],
                  ["402", "member_limit_reached", "The key creator's monthly limit is used."],
                  ["402", "key_limit_reached", "This key's monthly limit is used."],
                  ["402", "org_spend_limit_reached", "The organisation's monthly cap is used."],
                  ["422", "idempotency_key_reused", "The same Idempotency-Key with a different request."],
                  ["429", "rate_limited", "Too many requests; wait for Retry-After seconds."],
                ]}
              />
            </Section>

            <Section id="limits" title="Rate limits & retries">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="rounded-2xl border border-line bg-sf p-5 shadow-card">
                  <div className="text-[15.5px] font-medium text-ink">Rate limits</div>
                  <p className="mt-2 text-[14px] leading-relaxed text-ink2">
                    60 requests a minute per key and 300 per organisation. A refused request answers <C>429</C> with <C>Retry-After</C>, <C>X-RateLimit-Limit</C> and{" "}
                    <C>X-RateLimit-Remaining</C>.
                  </p>
                </div>
                <div className="rounded-2xl border border-line bg-sf p-5 shadow-card">
                  <div className="text-[15.5px] font-medium text-ink">Safe retries</div>
                  <p className="mt-2 text-[14px] leading-relaxed text-ink2">
                    Send an <C>Idempotency-Key</C> header on <C>POST /v1/verify</C>. A retry with the same key within 24 hours gets the first answer again, is not charged
                    twice, and carries <C>Idempotent-Replayed: true</C>.
                  </p>
                </div>
              </div>
            </Section>

            <Section id="safety" title="Keeping keys safe">
              <ul className="grid gap-3 sm:grid-cols-2">
                {[
                  "Keep keys on your server, never in an app or a web page.",
                  "Give each integration its own key, with a monthly limit and, if you can, an IP allowlist.",
                  "Rotate a key from the dashboard: the old one keeps working for 24 hours while you switch.",
                  "If a key leaks, revoke it at once.",
                ].map((t) => (
                  <li key={t} className="flex gap-3 rounded-2xl border border-line bg-sf p-4 text-[14px] leading-relaxed text-ink2 shadow-card">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="mt-0.5 shrink-0 text-acc-ink" aria-hidden="true">
                      <path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z" />
                      <path d="M9 12l2 2 4-4" />
                    </svg>
                    {t}
                  </li>
                ))}
              </ul>
            </Section>

            {/* Closing */}
            <div className="relative isolate mt-12 overflow-hidden rounded-[24px] bg-[#0f2a20] px-6 py-10 sm:px-10">
              <div aria-hidden="true" className="pointer-events-none absolute -right-20 -bottom-32 -z-10 h-[340px] w-[520px] rounded-full bg-[radial-gradient(closest-side,rgba(91,228,168,.3),transparent)] blur-2xl" />
              <div className="flex flex-wrap items-center justify-between gap-6">
                <div>
                  <div className="text-[1.6rem] font-medium tracking-tight text-white">Ready to build?</div>
                  <p className="mt-1 text-[15px] text-[#b9d3c6]">Create an organisation, add an API key and send your first check in minutes. ₹4 a check, no minimum.</p>
                </div>
                <Link href={`/signup?next=${encodeURIComponent("/app/org/new")}`} className="inline-flex h-11 items-center gap-2 rounded-[10px] bg-[#5be4a8] px-5 text-[15px] font-medium text-[#0b2018] hover:bg-[#7debbb]">
                  Get an API key
                </Link>
              </div>
            </div>
          </div>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
