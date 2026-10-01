import Link from "next/link";
import { DownloadHere, Features, HowItWorks, Pricing, ProductShot } from "@/components/landing";
import { SiteFooter, SiteHeader } from "@/components/site";
import { ApkFactsLine } from "@/lib/app-download";
import { EXTRA_CHECK_INR } from "@/lib/plans";

// The landing page: what Factify does, how, what it checks, the plans, the app, the
// API, questions. Quiet by design; only the laptop in "How it works" moves.

const arrow = (
  <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className="transition-transform group-hover:translate-x-0.5" aria-hidden="true">
    <path d="M3 8h10M9 4l4 4-4 4" />
  </svg>
);

const download = (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M12 4v11M7.5 10.5L12 15l4.5-4.5M5 19h14" />
  </svg>
);

const primary = "group inline-flex h-11 items-center gap-2 rounded-[10px] bg-acc px-5 text-[15px] font-medium text-on-acc transition-colors hover:bg-acc-h";
const ghost = "inline-flex h-11 items-center gap-2 rounded-[10px] border border-line2 px-5 text-[15px] font-medium text-ink transition-colors hover:bg-hover";

// How many sites web search may cite, counted by the API from the same list it uses
// (GET /v1/sources/summary); null when the API can't be reached, as during a build.
type SourceCounts = { sites: number; fact_checkers: number };

async function sourceCounts(): Promise<SourceCounts | null> {
  const api = (process.env.FACTIFY_API_INTERNAL || "http://localhost:8000").replace(/\/$/, "");
  try {
    const r = await fetch(`${api}/v1/sources/summary`, { next: { revalidate: 600 }, signal: AbortSignal.timeout(3000) });
    return r.ok ? ((await r.json()) as SourceCounts) : null;
  } catch {
    return null;
  }
}

const n = (value: number) => new Intl.NumberFormat("en-IN").format(value);

function facts(counts: SourceCounts | null) {
  return [
    counts ? [n(counts.sites), `trusted sites, ${n(counts.fact_checkers)} of them fact-checkers`] : ["Vetted", "publishers and fact-checkers only"],
    ["12", "languages, English and Indian"],
    ["5", "kinds of content"],
    ["0", "pictures, videos or PDFs stored after a check"],
  ];
}

function principles(counts: SourceCounts | null) {
  const list = counts ? `${n(counts.sites)} publishers, fact-checkers and official sites` : "Publishers, fact-checkers and official sites";
  return [
    ["A rulebook decides, not a chatbot.", "AI reads the pages; fixed rules make the call. Every verdict shows the sources it read and why it landed where it did."],
    [
      "Only sources worth trusting.",
      `${list}, chosen by published criteria: fact-checkers verified by the IFCN or EFCSN (now or in the past), wire services, public broadcasters and established newsrooms, and no outlets owned by politicians. Twenty copies of one wire story count once.`,
    ],
    ["Honest when unsure.", "Too new to confirm? You see “Unconfirmed” and the reason. Made-up news with a fake picture, reported by no one, is called out as False."],
  ];
}

const FAQ = [
  ["Is Factify a chatbot?", "No. AI finds the claims and reads the pages; a fixed rulebook makes the call, so the same claim gets the same answer on the website, the app and the API."],
  [
    "What happens when I reach my monthly limit?",
    `Your plan's checks start again on the 1st of each month. If you need more before then, move to a bigger plan or, on a paid plan, turn on extra usage at ₹${EXTRA_CHECK_INR} a check, with a monthly cap if you want one. A check that fails costs nothing. A paid plan doesn't renew by itself: pay again to continue, or it goes back to Free at the end of its month.`,
  ],
  [
    "Why isn't the app on the Play Store?",
    "It's coming. Until then you download it from our site and install it directly; Android asks you once to allow installs from your browser.",
  ],
  [
    "Do you keep what I check?",
    "Not against your name. Your list of past checks is kept in your browser or on your phone. The claims, sources and verdict of a check are stored without your name, so the same claim is answered faster next time. Pictures, videos and PDFs are read and never stored; we keep only a fingerprint of a picture, to recognise it if it's sent again. Location data is removed from photos before they're checked. In an organisation, the owner can turn on a shared history of the organisation's checks.",
  ],
];

export default async function Home() {
  const counts = await sourceCounts();
  const FACTS = facts(counts);
  const PRINCIPLES = principles(counts);
  return (
    <>
      <SiteHeader />
      <main>
        {/* Hero */}
        <section className="mx-auto max-w-[1200px] px-4 pt-20 pb-14 sm:px-8 sm:pt-26">
          <div className="flex max-w-[820px] flex-col gap-6.5">
            <h1 className="text-[2.9rem] leading-[1.02] font-medium tracking-[-0.045em] text-ink sm:text-[4.25rem]">
              Know what&apos;s true
              <br />
              <span className="text-ink3">before you forward it.</span>
            </h1>
            <p className="max-w-[600px] text-[19px] leading-relaxed text-ink2">
              Factify checks WhatsApp forwards, links, pictures, videos and PDFs against trusted newsrooms and fact-checkers — and shows you the line that proves it.
            </p>
            <div className="mt-1 flex flex-wrap items-center gap-3">
              <Link href="/signup" className={primary}>
                Start checking free {arrow}
              </Link>
              <Link href="/download" className={ghost}>
                {download} Download for Android
              </Link>
            </div>
            <span className="text-sm text-ink3">30 free checks every month. No card needed.</span>
          </div>
        </section>

        {/* The product, clickable */}
        <section className="mx-auto max-w-[1200px] px-4 pb-14 sm:px-8" aria-label="An example of Factify on the web">
          <ProductShot />
          <p className="mt-3.5 text-center text-[13px] text-ink3">An illustration with made-up example data, not a live account. Click the sidebar to see the other pages.</p>
        </section>

        {/* Quiet facts */}
        <section className="mx-auto max-w-[1200px] px-4 pb-10 sm:px-8">
          <div className="grid grid-cols-2 border-y border-line md:grid-cols-4">
            {FACTS.map(([value, label], i) => (
              <div key={label} className={`py-6.5 ${i % 2 ? "border-l border-line pl-5 sm:pl-7" : ""} ${i === 2 ? "md:border-l md:border-line md:pl-7" : ""} ${i >= 2 ? "max-md:border-t max-md:border-line" : ""}`}>
                <div className="text-[1.6rem] font-medium tracking-tight text-ink">{value}</div>
                <div className="mt-1 text-sm text-ink3">{label}</div>
              </div>
            ))}
          </div>
        </section>

        {/* How it works */}
        <section id="how" className="mx-auto max-w-[1200px] scroll-mt-20 px-4 pt-24 pb-10 sm:px-8 sm:pt-30">
          <HowItWorks />
        </section>

        {/* Features */}
        <section id="features" className="mx-auto max-w-[1200px] scroll-mt-20 px-4 pt-28 sm:px-8 sm:pt-36">
          <span className="eyebrow">Features</span>
          <div className="mt-3.5 grid items-end gap-6 md:grid-cols-2 md:gap-10">
            <h2 className="text-[2.2rem] leading-[1.08] font-medium tracking-tight text-ink sm:text-[2.75rem]">Whatever lands in your chats.</h2>
            <p className="max-w-[480px] text-lg leading-relaxed text-ink2">Paste it on the web or share it from WhatsApp. Factify reads English, Hindi and ten more Indian languages.</p>
          </div>
          <Features />
        </section>

        {/* Principles */}
        <section className="mx-auto max-w-[1200px] px-4 pt-28 sm:px-8 sm:pt-36">
          <div className="grid gap-10 md:grid-cols-3 md:gap-12">
            {PRINCIPLES.map(([title, body], i) => (
              <div key={title} className="flex flex-col gap-2.5">
                <span className="font-mono text-xs text-acc-ink">0{i + 1}</span>
                <h3 className="text-xl font-medium tracking-tight text-ink">{title}</h3>
                <p className="text-[15px] leading-relaxed text-ink2">{body}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Pricing */}
        <section id="pricing" className="mx-auto max-w-[1200px] scroll-mt-20 px-4 pt-32 sm:px-8 sm:pt-40">
          <Pricing />
        </section>

        {/* The app */}
        <section id="app" className="mx-auto max-w-[1200px] scroll-mt-20 px-4 pt-32 sm:px-8 sm:pt-40">
          <div className="grid overflow-hidden rounded-2xl border border-line bg-sf shadow-card lg:grid-cols-[minmax(0,1.1fr)_minmax(0,.9fr)]">
            <div className="flex flex-col gap-5 p-8 sm:p-14">
              <span className="eyebrow">Android app</span>
              <h2 className="text-[2rem] leading-[1.08] font-medium tracking-tight text-ink sm:text-[2.5rem]">Check straight from WhatsApp.</h2>
              <p className="max-w-[460px] text-[17px] leading-relaxed text-ink2">
                Long-press a forward, tap Share, choose Factify. The answer opens over your chat with a polite correction ready to send.
              </p>
              <div className="mt-2 flex flex-col gap-4">
                <DownloadHere />
                <ApkFactsLine className="text-[13.5px] text-ink3" />
                <Link href="/download" className={`${primary} self-start`}>
                  {download} Download the app
                </Link>
              </div>
              <span className="mt-2 text-[13.5px] text-ink3">On an iPhone? Use Factify in Safari — the app is Android-only for now.</span>
            </div>
            <div
              className="relative flex min-h-[460px] items-end justify-center overflow-hidden border-line lg:border-l"
              style={{ background: "radial-gradient(ellipse at 50% 110%, var(--glow), transparent 62%), var(--sf2)" }}
            >
              {/* A phone showing a chat in its light theme, with Factify's answer over it. */}
              <div className="-mb-11 h-[440px] w-[252px] rounded-t-[40px] border border-b-0 border-[#a6a9ad] bg-[#111214] px-2.5 pt-2.5 shadow-[0_0_0_3px_#c9cbce,0_40px_80px_-30px_rgba(0,0,0,.45)]" aria-hidden="true">
                <div className="relative h-full overflow-hidden rounded-t-[31px] bg-[#efeae2] text-[#111b21]">
                  <div className="flex h-5.5 items-center justify-between bg-white px-4.5 text-[10px] font-semibold">
                    <span>9:41</span>
                    <span className="h-3 w-13 rounded-lg bg-[#111214]" />
                    <span className="tracking-wider">▪▪▪</span>
                  </div>
                  <div className="flex h-11.5 items-center gap-2 border-b border-[#e9edef] bg-white px-3">
                    <span className="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-[#f2c46b] to-[#c98a2e] text-[11px] font-semibold text-white">F</span>
                    <span>
                      <span className="block text-[12.5px] font-semibold">Family group</span>
                      <span className="block text-[10px] text-[#667781]">Amma, Appa, Ravi, you</span>
                    </span>
                  </div>
                  <div className="flex flex-col gap-1.5 bg-[radial-gradient(rgba(17,27,33,.05)_1px,transparent_1.2px)] bg-[size:14px_14px] px-2.5 py-3">
                    <span className="self-center rounded-md bg-white px-2 py-0.5 text-[9.5px] text-[#54656f] shadow-[0_1px_.5px_rgba(11,20,26,.13)]">TODAY</span>
                    <div className="max-w-[84%] self-start rounded-[0_8px_8px_8px] bg-white px-2 pt-1.5 pb-1 text-[11.5px] leading-snug shadow-[0_1px_.5px_rgba(11,20,26,.13)]">
                      <div className="mb-0.5 text-[9.5px] text-[#8696a0] italic">↪ Forwarded many times</div>
                      <div className="text-[10.5px] font-semibold text-[#c98a2e]">Ravi</div>
                      Applications open for the National Sports Scholarship 2026-27. Apply today!
                      <div className="mt-0.5 text-right text-[9px] text-[#667781]">10:12</div>
                    </div>
                    <div className="max-w-[70%] self-end rounded-[8px_0_8px_8px] bg-[#d9fdd3] px-2 pt-1.5 pb-1 text-[11.5px] shadow-[0_1px_.5px_rgba(11,20,26,.13)]">
                      Is this real?
                      <div className="mt-0.5 text-right text-[9px] text-[#667781]">
                        10:13 <span className="text-[#53bdeb]">✓✓</span>
                      </div>
                    </div>
                  </div>
                  <div className="absolute inset-x-0 bottom-11 rounded-t-[20px] bg-white px-3.5 pt-2 pb-3.5 shadow-[0_-10px_30px_-8px_rgba(11,20,26,.22)]">
                    <div className="mx-auto mb-2.5 h-1 w-8.5 rounded-full bg-[#d1d7db]" />
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-[9px] tracking-[0.14em] text-[#0f7a58]">FACTIFY</span>
                      <span className="rounded-[5px] bg-[#fae8e4] px-1.5 py-0.5 text-[10px] font-medium text-[#c23a2e]">89% sure</span>
                    </div>
                    <div className="mt-0.5 text-2xl font-medium tracking-tight text-[#c23a2e]">False</div>
                    <div className="mt-0.5 mb-2.5 text-[11px] leading-snug text-[#474d49]">The government&apos;s fact-check unit says this scholarship is fake.</div>
                    <div className="flex h-8 items-center justify-center rounded-[9px] bg-[#0e6b4f] text-[11.5px] font-medium text-white">Copy correction</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Teams and the API */}
        <section id="teams" className="mx-auto max-w-[1200px] scroll-mt-20 px-4 pt-32 sm:px-8 sm:pt-40">
          <div className="grid items-center gap-12 lg:grid-cols-[minmax(0,.9fr)_minmax(0,1.1fr)] lg:gap-16">
            <div className="flex flex-col gap-4">
              <span className="eyebrow">Teams &amp; API</span>
              <h2 className="text-[2rem] leading-[1.08] font-medium tracking-tight text-ink sm:text-[2.5rem]">
                One shared pool.
                <br />
                One API.
              </h2>
              <p className="text-[17px] leading-relaxed text-ink2">Pool your team&apos;s checks, give each member a limit, create API keys for your tools and see usage by person and key.</p>
              <div className="mt-1.5 flex gap-5">
                <Link href="/signup?next=%2Fapp%2Forg%2Fnew" className="group inline-flex items-center gap-1.5 text-[15px] text-acc-ink">
                  Set up a team {arrow}
                </Link>
                <Link href="/docs" className="group inline-flex items-center gap-1.5 text-[15px] text-ink2 hover:text-ink">
                  API docs {arrow}
                </Link>
              </div>
            </div>
            <div className="overflow-hidden rounded-2xl border border-line bg-sf shadow-card">
              <div className="flex h-9.5 items-center gap-4 border-b border-line px-4 text-[12.5px] text-ink3">
                <span className="text-ink">Request and response</span>
                <span>shortened</span>
              </div>
              <pre className="overflow-x-auto p-5 font-mono text-[13px] leading-[1.9] text-ink2">
                <span className="text-acc-ink">curl</span> https://factify-zeai.indiasouthcentral.cloudapp.azure.com/v1/verify \{"\n"}
                {"  "}-H <span className="text-ink">&quot;Authorization: Bearer $FACTIFY_KEY&quot;</span> \{"\n"}
                {"  "}-H <span className="text-ink">&quot;Content-Type: application/json&quot;</span> \{"\n"}
                {"  "}-d <span className="text-ink">&apos;{"{"}&quot;text&quot;: &quot;Govt to pay ₹5,000 a month to every woman&quot;{"}"}&apos;</span>
                {"\n\n"}
                {"{ "}
                <span className="text-ink">&quot;verdict&quot;</span>: <span className="text-false">&quot;FALSE&quot;</span>, <span className="text-ink">&quot;confidence&quot;</span>: 89,{"\n"}
                {"  "}
                <span className="text-ink">&quot;summary&quot;</span>: &quot;…&quot;,{"\n"}
                {"  "}
                <span className="text-ink">&quot;claims&quot;</span>: [ {"{ "}
                <span className="text-ink">&quot;status&quot;</span>: <span className="text-false">&quot;CONTRADICTED&quot;</span>, <span className="text-ink">&quot;evidence&quot;</span>: [ … ] {"}"} ], … {"}"}
              </pre>
            </div>
          </div>
        </section>

        {/* FAQ */}
        <section id="faq" className="mx-auto max-w-[1200px] scroll-mt-20 px-4 pt-32 sm:px-8 sm:pt-40">
          <div className="grid gap-8 md:grid-cols-[minmax(0,.7fr)_minmax(0,1.3fr)] md:gap-16">
            <h2 className="text-[2rem] font-medium tracking-tight text-ink sm:text-[2.5rem]">Questions</h2>
            <div className="border-t border-line">
              {FAQ.map(([q, a]) => (
                <details key={q} className="group border-b border-line">
                  <summary className="flex cursor-pointer list-none items-center justify-between gap-4 py-5 text-base text-ink [&::-webkit-details-marker]:hidden">
                    {q}
                    <span className="text-[22px] font-light text-ink3 transition-transform duration-300 group-open:rotate-45">+</span>
                  </summary>
                  <p className="pb-5 text-[15px] leading-relaxed text-ink2">{a}</p>
                </details>
              ))}
            </div>
          </div>
        </section>

        {/* Closing */}
        <section className="mx-auto max-w-[1200px] px-4 pt-32 pb-32 text-center sm:px-8 sm:pt-40">
          <h2 className="text-[2.4rem] font-medium tracking-tight text-ink sm:text-[3.25rem]">Check your next forward.</h2>
          <div className="mt-7 flex flex-wrap justify-center gap-3">
            <Link href="/signup" className={primary}>
              Start checking free {arrow}
            </Link>
            <Link href="/download" className={ghost}>
              Download for Android
            </Link>
          </div>
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
