"use client";

// A check's answer: the verdict, then each claim with the sources behind it.

export type Evidence = {
  id: string;
  tier: string;
  direction: "supports" | "contradicts" | "contextualizes" | "risk_signal";
  finding: string;
  citation_url: string;
  source_excerpt: string;
  publisher: string | null;
  credibility?: string | null;
  observed_at?: string | null;
};

export type Claim = {
  id: string;
  text: string;
  status: "SUPPORTED" | "CONTRADICTED" | "MISLEADING_CONTEXT" | "UNVERIFIED";
  reason: string;
  confidence: number | null;
  explanation: string | null;
  evidence: Evidence[];
};

export type Verdict = {
  case_id: string;
  verdict: "TRUE" | "FALSE" | "PARTLY_TRUE" | "MISLEADING" | "UNCONFIRMED";
  confidence: number | null;
  summary: string | null;
  action_reason: string;
  claims: Claim[];
  advisories: { id: string; provider: string; note: string }[];
  completeness_note: string | null;
  from_cache?: boolean;
  elapsed_ms?: number | null;
};

export const verdictStyle: Record<Verdict["verdict"], { word: string; tone: string; soft: string }> = {
  TRUE: { word: "True", tone: "text-true", soft: "bg-true-soft" },
  FALSE: { word: "False", tone: "text-false", soft: "bg-false-soft" },
  PARTLY_TRUE: { word: "Partly true", tone: "text-mis", soft: "bg-mis-soft" },
  MISLEADING: { word: "Misleading", tone: "text-mis", soft: "bg-mis-soft" },
  UNCONFIRMED: { word: "Unconfirmed", tone: "text-unc", soft: "bg-unc-soft" },
};

const claimStyle: Record<Claim["status"], { word: string; tone: string; soft: string }> = {
  SUPPORTED: { word: "Supported", tone: "text-true", soft: "bg-true-soft" },
  CONTRADICTED: { word: "Contradicted", tone: "text-false", soft: "bg-false-soft" },
  MISLEADING_CONTEXT: { word: "Misleading", tone: "text-mis", soft: "bg-mis-soft" },
  UNVERIFIED: { word: "Not settled", tone: "text-unc", soft: "bg-unc-soft" },
};

const direction = {
  supports: ["Supports", "text-true"],
  contradicts: ["Refutes", "text-false"],
  contextualizes: ["Context", "text-mis"],
  risk_signal: ["Warning", "text-mis"],
} as const;

export function VerdictPill({ verdict }: { verdict: Verdict["verdict"] }) {
  const s = verdictStyle[verdict] ?? verdictStyle.UNCONFIRMED;
  return <span className={`inline-flex rounded-lg px-2.5 py-0.5 text-sm font-bold ${s.soft} ${s.tone}`}>{s.word}</span>;
}

function host(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export function Result({ result }: { result: Verdict }) {
  const s = verdictStyle[result.verdict] ?? verdictStyle.UNCONFIRMED;
  return (
    <div className="space-y-4">
      <div className={`rounded-2xl p-5 sm:p-6 ${s.soft}`}>
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className={`font-serif text-4xl font-semibold ${s.tone}`}>{s.word}</span>
          {result.confidence != null && <span className={`text-sm font-semibold ${s.tone}`}>{result.confidence}% sure</span>}
          {result.from_cache && <span className="text-xs text-ink3">answered before</span>}
        </div>
        {(result.summary || result.action_reason) && (
          <p className="mt-2 text-[15px] leading-relaxed text-ink">{result.summary || result.action_reason}</p>
        )}
        {result.completeness_note && <p className="mt-2 text-sm text-ink2">{result.completeness_note}</p>}
      </div>

      {result.advisories?.length > 0 && (
        <div className="rounded-2xl border border-line bg-sf p-4">
          <div className="mb-1 text-sm font-semibold text-ink">About the picture or video</div>
          <ul className="space-y-1 text-sm text-ink2">
            {result.advisories.map((a) => (
              <li key={a.id}>{a.note}</li>
            ))}
          </ul>
        </div>
      )}

      {result.claims.map((claim, i) => {
        const c = claimStyle[claim.status] ?? claimStyle.UNVERIFIED;
        return (
          <div key={claim.id} className="rounded-2xl border border-line bg-sf p-4 sm:p-5">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0">
                <div className="text-xs font-semibold text-ink3">Claim {i + 1}</div>
                <p className="mt-1 font-serif text-xl leading-snug text-ink">&ldquo;{claim.text}&rdquo;</p>
              </div>
              <span className={`shrink-0 self-start rounded-lg px-2.5 py-0.5 text-sm font-bold ${c.soft} ${c.tone}`}>{c.word}</span>
            </div>
            {(claim.explanation || claim.reason) && <p className="mt-2 text-[15px] text-ink2">{claim.explanation || claim.reason}</p>}
            {claim.evidence.length > 0 && (
              <ul className="mt-4 divide-y divide-line border-t border-line">
                {claim.evidence.map((e) => {
                  const [word, tone] = direction[e.direction] ?? ["Source", "text-ink2"];
                  return (
                    <li key={e.id} className="py-3">
                      <div className="flex items-center justify-between gap-3">
                        <a
                          href={e.citation_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="min-w-0 truncate font-semibold text-ink hover:text-acc-ink hover:underline"
                        >
                          {e.publisher || host(e.citation_url)}
                        </a>
                        <span className={`shrink-0 text-xs font-bold ${tone}`}>{word}</span>
                      </div>
                      {e.source_excerpt && <p className="mt-1 line-clamp-3 text-sm text-ink2">{e.source_excerpt}</p>}
                      <div className="mt-1 truncate text-xs text-ink3">{host(e.citation_url)}</div>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        );
      })}
    </div>
  );
}
