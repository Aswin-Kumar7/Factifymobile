import Link from "next/link";
import { SiteFooter, SiteHeader } from "@/components/site";

// The landing page. A first design: what Factify does, how, for whom, and prices.

const stamp = {
  FALSE: "border-false text-false",
  TRUE: "border-true text-true",
  MISLEADING: "border-mis text-mis",
};

function Example({
  source,
  text,
  verdict,
  tilt,
}: {
  source: string;
  text: string;
  verdict: keyof typeof stamp;
  tilt: string;
}) {
  return (
    <div className={`relative rounded-2xl border border-line bg-sf p-4 pb-7 shadow-[0_10px_30px_-18px_rgba(0,0,0,.35)] ${tilt}`}>
      <div className="text-xs italic text-ink3">{source}</div>
      <p className="mt-1.5 text-[15px] leading-snug text-ink">{text}</p>
      <span
        className={`absolute -bottom-3 right-4 rotate-[-8deg] rounded-lg border-2 bg-bg px-2.5 py-0.5 font-serif text-base font-semibold tracking-[0.12em] ${stamp[verdict]}`}
      >
        {verdict}
      </span>
    </div>
  );
}

const kinds = [
  ["Forwards and messages", "Paste a WhatsApp forward in any of 12 Indian languages."],
  ["News links", "We read the article and check each claim in it."],
  ["Pictures", "Text in the picture is read and checked; AI-made pictures are flagged."],
  ["Videos", "What's said is transcribed and checked; face swaps are flagged."],
  ["Voices in videos", "Machine-made voices in a video are flagged."],
  ["PDFs", "Circulars and documents, claim by claim."],
];

const steps = [
  ["Paste or share", "Text, a link, a picture, a video or a PDF - from the app, the website or the API."],
  ["We check each claim", "Published fact-checks, reliable news and official sources, read in full, in the claim's language."],
  ["See the evidence", "True, False, Misleading or Unconfirmed, with every source that supports or refutes it."],
];

const plans = [
  {
    name: "Free",
    price: "₹0",
    note: "for everyone",
    items: ["100 checks to start", "Phone app and website", "Every source shown", "Then packs from ₹249 for 50 checks"],
    cta: ["Start free", "/signup"],
  },
  {
    name: "Organisation",
    price: "from ₹5,999",
    note: "1,000 checks · credit packs, no subscription",
    items: [
      "One shared credit pool for your team",
      "Members with monthly limits",
      "API keys for your tools",
      "Usage by person and key, invoices",
    ],
    cta: ["Set up your team", "/signup?next=/app/org/new"],
    featured: true,
  },
  {
    name: "Newsroom",
    price: "Talk to us",
    note: "high volume",
    items: ["Larger packs", "Verified domain: your staff join automatically", "Single sign-on on request"],
    cta: ["Contact us", "mailto:aswin.aswin5640@gmail.com"],
  },
];

export default function Landing() {
  return (
    <>
      <SiteHeader />
      <main>
        <section className="mx-auto grid max-w-6xl items-center gap-12 px-4 pt-12 pb-16 sm:px-6 md:grid-cols-[1.1fr_1fr] md:pt-20 md:pb-24">
          <div>
            <p className="mb-4 inline-flex rounded-full bg-acc-soft px-3 py-1 text-sm font-semibold text-acc-ink">
              Fact-checking for India, in 12 languages
            </p>
            <h1 className="font-serif text-5xl leading-[1.02] font-medium tracking-tight text-ink sm:text-6xl lg:text-7xl">
              Know what&apos;s true before you share it
            </h1>
            <p className="mt-5 max-w-xl text-lg leading-relaxed text-ink2">
              Factify checks forwards, news links, pictures, videos and PDFs against reliable sources, and
              shows you every source it used. When the sources don&apos;t settle it, it says so.
            </p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <Link href="/signup" className="rounded-xl bg-acc px-6 py-3.5 text-center text-base font-semibold text-on-acc hover:brightness-110">
                Check something free
              </Link>
              <Link href="/#teams" className="rounded-xl border border-line bg-sf px-6 py-3.5 text-center text-base font-semibold text-ink hover:bg-sf2">
                For newsrooms and teams
              </Link>
            </div>
            <p className="mt-4 text-sm text-ink3">100 free checks. No card needed.</p>
          </div>
          <div className="space-y-8 md:pl-6">
            <Example
              source="Forwarded many times"
              text="Govt to pay ₹5,000 a month to every woman from 1 July. Register at the link…"
              verdict="FALSE"
              tilt="md:-rotate-2"
            />
            <Example
              source="rbi.org.in"
              text="RBI keeps repo rate unchanged in September review"
              verdict="TRUE"
              tilt="md:rotate-1 md:ml-10"
            />
            <Example
              source="Video · 0:42"
              text="Flooding inside Mumbai airport this morning"
              verdict="MISLEADING"
              tilt="md:-rotate-1 md:mr-8"
            />
          </div>
        </section>

        <section id="how" className="border-y border-line bg-sf">
          <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 md:py-20">
            <h2 className="font-serif text-4xl font-medium tracking-tight text-ink">How it works</h2>
            <div className="mt-10 grid gap-8 md:grid-cols-3">
              {steps.map(([title, body], i) => (
                <div key={title}>
                  <div className="flex h-10 w-10 items-center justify-center rounded-full bg-acc-soft font-serif text-xl font-semibold text-acc-ink">
                    {i + 1}
                  </div>
                  <h3 className="mt-4 text-lg font-semibold text-ink">{title}</h3>
                  <p className="mt-1.5 leading-relaxed text-ink2">{body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6 md:py-20">
          <h2 className="font-serif text-4xl font-medium tracking-tight text-ink">What it checks</h2>
          <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {kinds.map(([title, body]) => (
              <div key={title} className="rounded-2xl border border-line bg-sf p-5">
                <h3 className="font-semibold text-ink">{title}</h3>
                <p className="mt-1.5 text-[15px] leading-relaxed text-ink2">{body}</p>
              </div>
            ))}
          </div>
        </section>

        <section id="teams" className="bg-acc text-on-acc">
          <div className="mx-auto grid max-w-6xl gap-10 px-4 py-16 sm:px-6 md:grid-cols-2 md:py-20">
            <div>
              <h2 className="font-serif text-4xl font-medium tracking-tight">For newsrooms and teams</h2>
              <p className="mt-4 text-lg leading-relaxed opacity-90">
                One credit pool for your whole team. Give each person a monthly limit, let developers create API keys,
                and see who used what.
              </p>
              <Link href="/signup?next=/app/org/new" className="mt-8 inline-block rounded-xl bg-white px-6 py-3.5 font-semibold text-[#0e6b4f] hover:bg-white/90">
                Set up your organisation
              </Link>
            </div>
            <div className="min-w-0 rounded-2xl bg-black/25 p-4 font-mono text-[13px] leading-relaxed sm:p-5">
              <div className="opacity-70"># Check a forward from your own tools</div>
              <div className="break-all">curl https://&lt;factify&gt;/v1/verify \</div>
              <div className="break-all pl-4">-H &quot;Authorization: Bearer fct_live_…&quot; \</div>
              <div className="break-all pl-4">-d &apos;{`{"text": "Govt to pay ₹5,000 a month…"}`}&apos;</div>
              <div className="mt-3 opacity-70"># → verdict, claims, sources, credits used</div>
            </div>
          </div>
        </section>

        <section id="pricing" className="mx-auto max-w-6xl px-4 py-16 sm:px-6 md:py-20">
          <h2 className="font-serif text-4xl font-medium tracking-tight text-ink">Pricing</h2>
          <p className="mt-3 text-ink2">One check is one credit. A video is three.</p>
          <div className="mt-10 grid gap-5 lg:grid-cols-3">
            {plans.map((p) => (
              <div
                key={p.name}
                className={`flex flex-col rounded-2xl border bg-sf p-6 ${p.featured ? "border-acc ring-1 ring-acc" : "border-line"}`}
              >
                <h3 className="text-lg font-semibold text-ink">{p.name}</h3>
                <div className="mt-3 font-serif text-4xl font-medium text-ink">{p.price}</div>
                <div className="text-sm text-ink3">{p.note}</div>
                <ul className="mt-5 flex-1 space-y-2 text-[15px] text-ink2">
                  {p.items.map((item) => (
                    <li key={item} className="flex gap-2">
                      <span className="text-acc-ink">✓</span>
                      {item}
                    </li>
                  ))}
                </ul>
                <Link
                  href={p.cta[1]}
                  className={`mt-6 rounded-xl py-3 text-center font-semibold ${p.featured ? "bg-acc text-on-acc" : "border border-line text-ink hover:bg-sf2"}`}
                >
                  {p.cta[0]}
                </Link>
              </div>
            ))}
          </div>
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
