import type { Metadata } from "next";
import { Prose, SiteFooter, SiteHeader } from "@/components/site";

export const metadata: Metadata = { title: "API docs" };

function Code({ children }: { children: string }) {
  return (
    <pre className="my-4 overflow-x-auto rounded-xl bg-[#1c1b18] p-4 font-mono text-[13px] leading-relaxed text-[#f1efe8]">
      <code className="!bg-transparent !p-0">{children}</code>
    </pre>
  );
}

const BASE = "https://factify-zeai.indiasouthcentral.cloudapp.azure.com";

export default function Docs() {
  return (
    <>
      <SiteHeader />
      <Prose>
        <h1>API</h1>
        <p>
          Check text, links, pictures, PDFs and videos from your own tools. The API is for organisations: an owner or
          developer creates a key in the dashboard under <strong>API keys</strong>, and every check is paid from the
          organisation&apos;s credit pool.
        </p>

        <h2>Authentication</h2>
        <p>Send your key as a bearer token. Keys start with <code>fct_live_</code> and are shown only once.</p>
        <Code>{`Authorization: Bearer fct_live_…`}</Code>

        <h2>Check text or a link</h2>
        <p>
          <code>POST /v1/verify</code> with exactly one of <code>text</code> or <code>url</code>. The answer comes back
          in the same request (usually 20-60 seconds).
        </p>
        <Code>{`curl ${BASE}/v1/verify \\
  -H "Authorization: Bearer $FACTIFY_KEY" \\
  -H "Content-Type: application/json" \\
  -H "Idempotency-Key: 6f1c2a9e-order-4411" \\
  -d '{"text": "Govt to pay ₹5,000 a month to every woman from 1 July."}'`}</Code>
        <p>
          For a long check, send <code>&quot;mode&quot;: &quot;background&quot;</code>: you get <code>202</code> with a{" "}
          <code>case_id</code> at once, then poll <code>GET /v1/cases/&#123;case_id&#125;</code> until it answers{" "}
          <code>200</code>.
        </p>

        <h3>Python</h3>
        <Code>{`import os, requests

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
        print("   ", source["direction"], source["citation_url"])`}</Code>

        <h3>JavaScript</h3>
        <Code>{`const r = await fetch("${BASE}/v1/verify", {
  method: "POST",
  headers: {
    Authorization: \`Bearer \${process.env.FACTIFY_KEY}\`,
    "Content-Type": "application/json",
  },
  body: JSON.stringify({ text: "RBI keeps repo rate unchanged" }),
});
const answer = await r.json();
console.log(answer.verdict, r.headers.get("Factify-Credits-Remaining"));`}</Code>

        <h2>Check a picture, PDF or video</h2>
        <p>
          <code>POST /v1/verify/file</code> as a multipart form with <code>file</code> and{" "}
          <code>consent_to_process_media=true</code>. A video always answers <code>202</code>; poll its{" "}
          <code>case_id</code>.
        </p>
        <Code>{`curl ${BASE}/v1/verify/file \\
  -H "Authorization: Bearer $FACTIFY_KEY" \\
  -F file=@photo.jpg -F consent_to_process_media=true`}</Code>

        <h2>The answer</h2>
        <p>
          <code>verdict</code> is <code>TRUE</code>, <code>FALSE</code>, <code>MISLEADING</code> or{" "}
          <code>UNCONFIRMED</code>, with a <code>confidence</code> and a plain <code>summary</code>. Each of the{" "}
          <code>claims</code> has its own status and <code>evidence</code>: the source&apos;s URL, publisher, the
          excerpt that was read, and whether it supports or refutes the claim. The full schema is at{" "}
          <a href={`${BASE}/openapi.json`}>/openapi.json</a> (OpenAPI).
        </p>

        <h2>Credits</h2>
        <div className="-mx-4 overflow-x-auto px-4">
        <table className="min-w-[520px]">
          <thead>
            <tr>
              <th>Check</th>
              <th>Credits</th>
            </tr>
          </thead>
          <tbody>
            <tr><td>Text, a link, a picture or a PDF</td><td>1</td></tr>
            <tr><td>A video</td><td>3</td></tr>
            <tr><td>An answer already known (from the cache)</td><td>1</td></tr>
            <tr><td>A check that fails</td><td>0</td></tr>
          </tbody>
        </table>
        </div>
        <p>
          Each response carries <code>Factify-Credits-Used</code> and <code>Factify-Credits-Remaining</code> headers.
          Credits are held when a check starts and charged when it has its answer, so parallel requests can never
          spend more than the pool, the member&apos;s limit or the key&apos;s limit allows.
        </p>

        <h2>Retries</h2>
        <p>
          Send an <code>Idempotency-Key</code> header (any unique string) on <code>POST /v1/verify</code>. A retry with
          the same key within 24 hours gets the first answer again, and is not charged twice. The replay carries{" "}
          <code>Idempotent-Replayed: true</code>.
        </p>

        <h2>Errors</h2>
        <p>
          Every error has a JSON body with <code>detail</code> (for people) and <code>error_code</code> (for programs).
        </p>
        <div className="-mx-4 overflow-x-auto px-4">
        <table className="min-w-[520px]">
          <thead>
            <tr>
              <th>Status</th>
              <th>error_code</th>
              <th>Meaning</th>
            </tr>
          </thead>
          <tbody>
            <tr><td>401</td><td><code>invalid_api_key</code></td><td>Unknown, mistyped, revoked or expired key</td></tr>
            <tr><td>403</td><td><code>key_not_allowed</code></td><td>Organisation suspended, key&apos;s creator removed, or IP not allowed</td></tr>
            <tr><td>402</td><td><code>insufficient_credits</code></td><td>The pool can&apos;t pay for this check</td></tr>
            <tr><td>402</td><td><code>member_limit_reached</code></td><td>The key creator&apos;s monthly limit is used</td></tr>
            <tr><td>402</td><td><code>key_limit_reached</code></td><td>This key&apos;s monthly limit is used</td></tr>
            <tr><td>402</td><td><code>org_spend_limit_reached</code></td><td>The organisation&apos;s monthly cap is used</td></tr>
            <tr><td>429</td><td><code>rate_limited</code></td><td>Too many requests; wait for <code>Retry-After</code> seconds</td></tr>
            <tr><td>422</td><td><code>idempotency_key_reused</code></td><td>The same Idempotency-Key with a different request</td></tr>
          </tbody>
        </table>
        </div>

        <h2>Rate limits</h2>
        <p>
          60 requests a minute per key and 300 per organisation. A refused request answers <code>429</code> with{" "}
          <code>Retry-After</code>, <code>X-RateLimit-Limit</code> and <code>X-RateLimit-Remaining</code>.
        </p>

        <h2>Keeping keys safe</h2>
        <ul>
          <li>Keep keys on your server, never in an app or a web page.</li>
          <li>Give each integration its own key, with a monthly limit and, if you can, an IP allowlist.</li>
          <li>Rotate a key from the dashboard: the old one keeps working for 24 hours while you switch.</li>
          <li>If a key leaks, revoke it at once.</li>
        </ul>
      </Prose>
      <SiteFooter />
    </>
  );
}
