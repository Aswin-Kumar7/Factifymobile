"use client";

// A check's answer, shown exactly as the phone app shows it (apps/mobile/lib/widgets/
// verdict_card.dart and picture_checks.dart): the same verdict word and line, the
// same "nothing to fact-check" for a picture with no claim in it, the picture or
// video checks, what was read in a picture or heard in a video, what is right and
// what is wrong, the sources, the correction to send back, and a way to report a
// wrong result. The wording is the app's own English (app_en.arb).
//
// It was a plain list of claims and the server's advisory notes. A picture whose
// own file says an AI tool made it, with nothing in it to fact-check, read
// "Unconfirmed - the sources we could find do not confirm or rule this out" on the
// website, while the phone said "Nothing to fact-check" and "its content credentials
// say it was made with an AI tool" (2026-10-01).
//
// Since 1.8 the answer also says what was read (`input_read`), and holds the verdict
// back when what could not be read could decide it: "Not checked yet", with a way to
// send the rest or to check only what was read. See what-we-read.tsx.

import { useState } from "react";
import { Button } from "@/components/ui";
import { api } from "@/lib/api";
import {
  blocked,
  day,
  host,
  IMAGE_KIND,
  InputRead,
  Mark,
  MARK,
  MarkKey,
  markOf,
  missedMedia,
  PARTLY_READ_REASON,
  readAny,
  readEnough,
  readNoun,
  served,
  spansIn,
  Underlined,
  WhatWeRead,
} from "@/components/what-we-read";

type Evidence = {
  id: string;
  tier: string;
  kind?: string;
  direction: "supports" | "contradicts" | "contextualizes" | "risk_signal";
  finding: string;
  citation_url: string;
  source_excerpt: string;
  publisher: string | null;
  credibility?: string | null;
  observed_at?: string | null;
  published_on?: string | null;
  title?: string | null;
  match_basis?: { metric?: string; value?: number; threshold?: number } | null;
  earlier_media?: { thumbnail_url?: string | null; published_at?: string | null; publisher?: string | null; similarity?: number | null } | null;
  input_anchor?: { char_start?: number | null; char_end?: number | null } | null;
};

export type Claim = {
  id: string;
  text: string;
  claim_type?: string;
  importance?: string;
  status: "SUPPORTED" | "CONTRADICTED" | "MISLEADING_CONTEXT" | "UNVERIFIED";
  reason: string;
  rule_id?: string | null;
  confidence: number | null;
  explanation: string | null;
  evidence: Evidence[];
  search?: string | null;
  sources_looked_at?: number | null;
  technique?: string | null;
  in_full?: string | null;
  language?: string | null;
  input_anchor?: { char_start?: number | null; char_end?: number | null } | null;
};

type MediaReport = {
  kind?: string;
  frames?: number | null;
  credentials?: { status?: string; signer?: string | null; declares_ai?: boolean; generator?: string | null };
  history?: {
    status?: string;
    why?: string | null;
    pages?: number;
    dated?: number;
    earliest?: { url: string; published_at?: string; publisher?: string | null; days_before?: number | null; thumbnail_url?: string | null } | null;
  };
  detector?: {
    status?: string;
    why?: string | null;
    generated?: number | null;
    face_swap?: number | null;
    second_opinion?: number | null;
    agreement?: string | null;
    faces?: number | null;
    voice?: number | null;
    on_server?: boolean;
    machine_voice?: boolean | null;
    face_swapped?: boolean | null;
  };
  editing?: { status?: string; uneven_noise?: boolean; spectral_peaks?: boolean };
};

export type Verdict = {
  case_id: string;
  action?: string;
  verdict: "TRUE" | "FALSE" | "PARTLY_TRUE" | "MISLEADING" | "UNCONFIRMED";
  confidence: number | null;
  summary: string | null;
  action_reason: string;
  claims: Claim[];
  advisories: { id: string; provider: string; note: string }[];
  // `kind` (1.8): reading | deadline | provider | other.
  skipped?: { check: string; reason: string; kind?: string }[];
  completeness_note: string | null;
  from_cache?: boolean;
  elapsed_ms?: number | null;
  retrieved_at?: string | null;
  receipt?: { receipt_id?: string; verified?: boolean } | null;
  image_reading?: { text?: string; description?: string | null; kind?: string | null; publisher?: string | null; language?: string | null } | null;
  // For a post: its first picture's checks; `media_reports` has pictures 2 to n (1.8).
  media_report?: MediaReport | null;
  media_reports?: MediaReport[];
  speech?: { text?: string; language?: string | null; cut_off?: boolean } | null;
  // What was read, part by part, and what could not be (1.8). None on older cases.
  input_read?: InputRead | null;
  source_risk?: string | null;
  source_profile?: {
    domain: string;
    trusted: boolean;
    trust?: string | null;
    fact_checker?: boolean;
    level?: string;
    findings?: string[];
    warnings?: string[];
    domain_age_days?: number | null;
  } | null;
  recurrence?: { times_seen?: number; first_verified_at?: string | null; distinct_captions?: number; summary: string } | null;
};

// ---------------------------------------------------------------- words

const VERDICT = {
  TRUE: { word: "True", line: "Reliable sources confirm this", tone: "text-true", soft: "bg-true-soft", grad: "from-true-soft" },
  FALSE: { word: "False", line: "Reliable sources show this is false", tone: "text-false", soft: "bg-false-soft", grad: "from-false-soft" },
  PARTLY_TRUE: { word: "Partly true", line: "Some of this is right, some of it isn't", tone: "text-mis", soft: "bg-mis-soft", grad: "from-mis-soft" },
  MISLEADING: { word: "Misleading", line: "True in part, but missing important context", tone: "text-mis", soft: "bg-mis-soft", grad: "from-mis-soft" },
  UNCONFIRMED: { word: "Unconfirmed", line: "We couldn't confirm or rule this out yet", tone: "text-unc", soft: "bg-unc-soft", grad: "from-unc-soft" },
} as const;

const NOTHING = { word: "Nothing to fact-check", line: "No claim found in it", tone: "text-unc", soft: "bg-unc-soft", grad: "from-unc-soft" };

const UNCONFIRMED_BODY =
  "We couldn't find enough reliable sources that address this directly. Treat it with caution until it's confirmed.";

const ORDER: Mark[] = ["wrong", "partly", "context", "right", "unconfirmed"];

const TECHNIQUE: Record<string, [string, string]> = {
  RECYCLED_MEDIA: ["Recycled picture", "A picture published earlier, shared again as if it showed something new. Before trusting a photo, look for when it first appeared."],
  MISSING_CONTEXT: ["Missing context", "Published material framed to suggest something its sources do not say. Ask what the post leaves out."],
  MISATTRIBUTED_QUOTE: ["Words put in someone's mouth", "A quote credited to someone that published sources do not record them saying. Look for the original speech or statement."],
  TWISTED_NUMBER: ["Twisted number", "A figure changed, or taken from a source that says something different. Find the number in its original source."],
  WRONG_IDENTITY: ["Wrong label", "A person or place presented as someone or somewhere else. Check names and places against a dated source."],
};

// ---------------------------------------------------------------- rules (as the app)

// Checks that are about reading the input, not checking it: with one of these skipped,
// an empty answer is never "nothing to fact-check" - something may not have been read.
// After the first three are what part of a link, a post or an upload that could not
// be read is reported as (1.8); a 1.8 server also marks such a skip `kind: "reading"`.
const READING_CHECKS = new Set([
  "claim_extraction",
  "image_text",
  "document_text",
  "linked_page",
  "post_text",
  "video",
  "speech",
  "video_text",
  "input",
]);

// Said among the skipped checks, but a note of what was read, not something missed:
// "read the words on 12 frames taken from 0:00 to 0:48" on every video.
const NOTES = new Set(["video_frames"]);

const isReadingSkip = (s: { check: string; kind?: string }) => s.kind === "reading" || READING_CHECKS.has(s.check);

/** Nothing in it a source could settle: no claim, only opinion, or only a picture's
 * own history with no earlier copy found. Not "unconfirmed" - there is nothing to
 * confirm. Never when reading failed. (Verdict.nothingToCheck in the app.) */
function nothingToCheck(v: Verdict): boolean {
  if (v.verdict !== "UNCONFIRMED") return false;
  const quiet = v.claims.every(
    (c) => (c.claim_type === "MEDIA" && c.status === "UNVERIFIED" && c.evidence.length === 0) || c.claim_type === "OPINION",
  );
  return quiet && !v.input_read?.verdict_withheld && !unread(v);
}

/** Part of the input that could decide the answer was not read. With the reading in
 * hand its blocking gaps say so - a long article's unread tail does not make an empty
 * answer anything but empty - or claims could not be looked for at all; without it,
 * any reading check that was skipped. */
function unread(v: Verdict): boolean {
  const skipped = v.skipped ?? [];
  if (v.input_read) {
    return (v.input_read.gaps ?? []).some((g) => g.blocking) || skipped.some((s) => s.check === "claim_extraction" && s.kind !== "reading");
  }
  return skipped.some((s) => READING_CHECKS.has(s.check));
}

/** Held back: what could not be read could decide the answer, so none was given. */
function withheldOf(v: Verdict): boolean {
  return !!v.input_read?.verdict_withheld;
}

/** Checked from part of the input, as the person asked ("Check what was read"). A
 * case stored without its reading still says so by the partly-read rule's reason. */
function partlyReadOf(v: Verdict): boolean {
  return !!v.input_read?.checked_partially || partlySupported(v);
}

/** Checked from part of the input with all of that part supported: "wait and
 * re-check" under rollup.partly_read, never TRUE. Told apart from news too recent to
 * confirm - the same action - by the rule's fixed reason, not by the action. */
function partlySupported(v: Verdict): boolean {
  return v.action_reason === PARTLY_READ_REASON;
}

/** Finding the claims failed (the model did not answer, or answered nothing usable),
 * so nothing the input says was searched for. Not the reading skip a withheld answer
 * carries (`kind: "reading"`), not an input with no words to look in, and not when
 * claims were found all the same. */
function extractionFailed(v: Verdict): boolean {
  return (
    (v.skipped ?? []).some((s) => s.check === "claim_extraction" && s.kind !== "reading" && !/^no text to extract/i.test(s.reason ?? "")) &&
    !v.claims.some((c) => c.claim_type !== "MEDIA")
  );
}

const INCOMPLETE = "Not everything could be checked, so this answer may be incomplete.";

/** The sentence under the verdict when not everything could be checked, by why: the
 * time running out only when it did (`kind: "deadline"`). A reading gap is said in
 * the reading panel instead; a case stored before 1.8 has none, so it is said here.
 * Finding the claims failing is said in the summary (`extractionFailed`). */
function incompleteLine(v: Verdict): string | null {
  const checking = (v.skipped ?? []).filter((s) => !isReadingSkip(s) && !NOTES.has(s.check));
  // A server before 1.8, and the pipeline's own timeouts until they are marked, send
  // every skip as "other"; their reasons ("deadline of 55s exceeded", TimeoutError)
  // still say the time ran out.
  const outOfTime = checking.some((s) => s.kind === "deadline" || ((s.kind ?? "other") === "other" && /deadline|timed? ?out/i.test(s.reason ?? "")));
  if (outOfTime) return "Some sources couldn't be checked in time, so this answer may be incomplete.";
  if (checking.some((s) => s.kind === "provider")) return "A service Factify relies on didn't answer, so this answer may be incomplete.";
  // Only what the check itself missed is in `completeness_note`; a note added after it
  // (what was read of a video) is not something missed.
  if (!v.completeness_note) return null;
  if (checking.length) return INCOMPLETE;
  return v.input_read ? null : "Not everything could be read or checked, so this answer may be incomplete.";
}

/** The claim a check is mainly about; never a picture's MEDIA question. */
export function headlineOf(v: Verdict): string | null {
  const said = v.claims.filter((c) => c.claim_type !== "MEDIA");
  return (said.find((c) => c.importance === "HEADLINE") ?? said[0])?.text ?? null;
}

// The languages the message to send back is written in (CorrectionTextRequest).
const CORRECTION_LANGUAGES = new Set(["en", "hi", "bn", "mr", "te", "ta", "gu", "ur", "kn", "or", "ml", "pa"]);

/** The language to write the correction in: the language of what was checked - the
 * main claim's, else the first part read that has one (a post's text, a picture's
 * words, a video's speech) - when the message can be written in it; English otherwise
 * (Hinglish too, as the server writes it). */
function correctionLanguage(v: Verdict): string {
  const said = v.claims.filter((c) => c.claim_type !== "MEDIA");
  const main = said.find((c) => c.importance === "HEADLINE") ?? said[0];
  const read = v.input_read?.parts?.find((p) => p.checked && p.language)?.language;
  const language = (main?.language || read || v.image_reading?.language || v.speech?.language || "en").toLowerCase();
  return CORRECTION_LANGUAGES.has(language) ? language : "en";
}

/** What a kept check is labelled with: its verdict, NOTHING, or WITHHELD when the
 * verdict was held back because part of the input could not be read. */
export function labelOf(v: Verdict): Label {
  if (withheldOf(v)) return "WITHHELD";
  return nothingToCheck(v) ? "NOTHING" : v.verdict;
}

export type Label = Verdict["verdict"] | "NOTHING" | "WITHHELD";

const decisive = (c: Claim) => c.status !== "UNVERIFIED";
const isNarrower = (e: Evidence) => (e.match_basis?.metric ?? "").startsWith("passage_narrower");
const isMediaMatch = (e: Evidence) => e.kind === "media_match";

function plural(n: number, one: string, many: string) {
  return n === 1 ? one : many.replace("{n}", String(n));
}

function claimReason(c: Claim): string {
  if (decisive(c)) return c.explanation?.trim() ? c.explanation : c.reason;
  const taking = c.evidence.filter((e) => e.direction === "supports" || e.direction === "contradicts").length;
  const looked = c.sources_looked_at ?? 0;
  switch (c.search) {
    case "not_searched":
      return "This claim wasn't checked: an older version of Factify checked only three claims. Check it again.";
    case "unavailable":
      if (taking === 0) return "Our news search couldn't be reached, so no news reports were looked at for this. It isn't the same as finding nothing.";
      break;
    case "timed_out":
      if (taking === 0) return "No source for this could be read in time. Check it again.";
      break;
    case "searched":
      if (taking === 1) return "Only one source addressed this. We need two independent ones before calling it true.";
      if (taking === 0 && looked > 0) return `We read ${plural(looked, "1 source", "{n} sources")} and none addressed this directly.`;
      if (taking === 0) return "We searched trusted news and fact-checkers and found nothing that addresses this.";
  }
  return UNCONFIRMED_BODY;
}

function techniqueOf(v: Verdict): [string, string] | null {
  for (const c of v.claims) {
    if (c.technique && TECHNIQUE[c.technique]) return TECHNIQUE[c.technique];
    const contradicted = c.status === "CONTRADICTED";
    const context = c.status === "MISLEADING_CONTEXT";
    if (!contradicted && !context) continue;
    if (c.claim_type === "MEDIA" && c.evidence.some(isMediaMatch)) return TECHNIQUE.RECYCLED_MEDIA;
    if (context) return TECHNIQUE.MISSING_CONTEXT;
    if (c.claim_type === "QUOTE" || c.claim_type === "ATTRIBUTION") return TECHNIQUE.MISATTRIBUTED_QUOTE;
    if (c.claim_type === "STATISTIC") return TECHNIQUE.TWISTED_NUMBER;
    if (c.claim_type === "IDENTITY") return TECHNIQUE.WRONG_IDENTITY;
  }
  return null;
}

/** Every page cited once, only those that take a side (or show a smaller version),
 * the ones that decided the verdict first. */
function sourcesOf(v: Verdict): Evidence[] {
  const seen = new Set<string>();
  const all: Evidence[] = [];
  for (const c of v.claims) {
    for (const e of c.evidence) {
      if (e.direction === "risk_signal" || isMediaMatch(e)) continue;
      if (e.direction !== "supports" && e.direction !== "contradicts" && !isNarrower(e)) continue;
      if (!seen.has(e.citation_url)) {
        seen.add(e.citation_url);
        all.push(e);
      }
    }
  }
  const leading = v.verdict === "FALSE" ? "contradicts" : v.verdict === "TRUE" ? "supports" : null;
  if (leading) all.sort((a, b) => Number(b.direction === leading) - Number(a.direction === leading));
  return all;
}

function aiNote(v: Verdict): string | null {
  const r = v.media_report;
  if (!r || !nothingToCheck(v)) return null;
  const video = r.kind === "video";
  const notes: string[] = [];
  if (r.credentials?.declares_ai) notes.push("But its content credentials say it was made with an AI tool. See the checks below.");
  else if (r.detector?.agreement === "likely_ai")
    notes.push(
      video
        ? "But our checks say this video was likely made by AI. See the video checks below."
        : "But our AI-picture check says this picture was likely made by AI. See the picture checks below.",
    );
  if (video && r.detector?.face_swapped)
    notes.push(notes.length ? "A face in it was also likely swapped or changed by AI." : "But our checks say a face in this video was likely swapped or changed by AI. See the video checks below.");
  if (video && r.detector?.machine_voice)
    notes.push(
      notes.length
        ? "Its voice was also likely made by a computer."
        : "But our checks say the voice in this video was likely made by a computer, not recorded from a person. See the video checks below.",
    );
  return notes.length ? notes.join(" ") : null;
}

// ---------------------------------------------------------------- pieces

export function VerdictPill({ verdict }: { verdict: Label }) {
  const s =
    verdict === "NOTHING"
      ? { ...NOTHING, word: "Nothing to check" }
      : verdict === "WITHHELD"
        ? { ...NOTHING, word: "Not checked yet" }
        : (VERDICT[verdict] ?? VERDICT.UNCONFIRMED);
  return <span className={`inline-flex shrink-0 rounded-md px-2 py-0.5 text-xs font-medium ${s.soft} ${s.tone}`}>{s.word}</span>;
}

function Section({ title, note }: { title: string; note?: string }) {
  return (
    <div className="mb-2.5 mt-6 flex flex-wrap items-baseline justify-between gap-x-3 px-1">
      <h3 className="text-base font-medium text-ink">{title}</h3>
      {note && <span className="text-xs text-ink3">{note}</span>}
    </div>
  );
}

function Box({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={`rounded-[14px] border border-line bg-sf shadow-card ${className}`}>{children}</div>;
}

function Meter({ value, label, raised }: { value: number; label: string; raised?: boolean }) {
  const up = raised ?? value >= 0.7;
  return (
    <div className="mt-2">
      <div className={`text-sm ${up ? "font-semibold text-mis" : "font-medium text-ink"}`}>{label}</div>
      <div className="mt-1.5 h-1.5 overflow-hidden rounded bg-line">
        <div className={`h-full rounded ${up ? "bg-mis" : "bg-ink3"}`} style={{ width: `${Math.round(Math.min(1, Math.max(0, value)) * 100)}%` }} />
      </div>
    </div>
  );
}

function Line({ children, raised, quiet }: { children: React.ReactNode; raised?: boolean; quiet?: boolean }) {
  return <p className={`text-sm leading-snug ${raised ? "font-semibold text-mis" : quiet ? "text-ink3" : "font-medium text-ink"}`}>{children}</p>;
}

function CheckRow({ title, children, href }: { title: string; children: React.ReactNode; href?: string }) {
  const body = (
    <div className="px-4 py-3.5">
      <div className="mb-1 text-xs font-semibold text-ink3">{title}</div>
      <div className="space-y-1">{children}</div>
    </div>
  );
  return href ? (
    <a href={href} target="_blank" rel="noopener noreferrer" className="block hover:bg-sf2">
      {body}
    </a>
  ) : (
    body
  );
}

const pct = (v: number) => Math.round(v * 100);

function age(days: number) {
  if (days >= 365) return plural(Math.floor(days / 365), "1 year", "{n} years");
  if (days >= 60) return plural(Math.floor(days / 30), "1 month", "{n} months");
  return plural(days, "1 day", "{n} days");
}

/** A small picture with its caption. Our own copies are kept for an hour, so one
 * opened later from History is gone (404): then neither is shown. */
function Figure({ src, caption }: { src: string; caption: string }) {
  const [gone, setGone] = useState(false);
  if (gone) return null;
  return (
    <figure>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={src} alt={caption} onError={() => setGone(true)} className="h-[72px] w-24 rounded-lg bg-sf2 object-cover" />
      <figcaption className="mt-1 text-xs text-ink3">{caption}</figcaption>
    </figure>
  );
}

function PictureChecks({ report, preview, footnote = true }: { report: MediaReport; preview?: string | null; footnote?: boolean }) {
  const cred = report.credentials ?? {};
  const hist = report.history ?? {};
  const det = report.detector ?? {};
  const edit = report.editing ?? {};
  const earliest = hist.earliest ?? null;
  const likelyAi = det.agreement === "likely_ai";
  const agreement =
    det.agreement === "likely_ai"
      ? det.second_opinion == null
        ? "The detector says this is likely AI-made"
        : "Both detectors say this is likely AI-made"
      : det.agreement === "unclear"
        ? "The detectors disagree, so it's unclear"
        : det.agreement === "no_sign"
          ? "No sign that an AI generator made it. That doesn't prove it's real."
          : null;
  const detWhy =
    { text_card: "Not needed: this is a text card or a screenshot, so the words in it are checked instead.", too_small: "The picture is too small to judge.", unreadable: "The picture could not be read.", off: "The AI-picture check is not set up on this server.", failed: "It could not be checked this time. Try again later." }[
      det.why ?? ""
    ] ?? null;
  const detNothing = det.generated == null && det.face_swap == null && det.voice == null;

  return (
    <>
      <Box className="divide-y divide-line">
        <CheckRow title="Content credentials">
          {cred.declares_ai && (
            <Line raised>{cred.generator ? `The file says it was made with an AI tool (${cred.generator})` : "The file says it was made with an AI tool"}</Line>
          )}
          {cred.status === "valid" ? (
            <Line>Signed by {cred.signer ?? ""}</Line>
          ) : cred.status === "untrusted" ? (
            <Line>Present, but the signer isn&apos;t verified</Line>
          ) : cred.status === "invalid" ? (
            <Line>Present, but they don&apos;t check out</Line>
          ) : cred.status === "none" ? (
            cred.declares_ai ? null : <Line quiet>None. That&apos;s normal: most pictures carry none.</Line>
          ) : (
            <Line quiet>Not checked</Line>
          )}
        </CheckRow>

        <CheckRow title="Earlier copies online" href={earliest?.url}>
          {hist.status === "found" && earliest ? (
            <>
              <Line>
                Online since {day(earliest.published_at) ?? "an earlier date"} · {earliest.publisher?.trim() || host(earliest.url)}
              </Line>
              {(earliest.days_before ?? 0) >= 30 && <Line raised>Not a new picture: it was online {age(earliest.days_before!)} before this check.</Line>}
              {earliest.thumbnail_url && (
                <div className="mt-2 flex gap-3">
                  {preview && <Figure src={preview} caption="Your picture" />}
                  <Figure src={served(earliest.thumbnail_url)} caption="Earlier copy" />
                </div>
              )}
            </>
          ) : hist.status === "found" ? (
            <Line>{plural(hist.pages ?? 0, "Found on 1 page, with no date", "Found on {n} pages, none dated")}</Line>
          ) : hist.status === "none" ? (
            <Line>No earlier copies found online</Line>
          ) : (
            <>
              <Line quiet>Not checked</Line>
              {hist.why === "off" && <Line quiet>Searching for earlier copies is not set up on this server.</Line>}
              {hist.why === "failed" && <Line quiet>It could not be checked this time. Try again later.</Line>}
            </>
          )}
        </CheckRow>

        <CheckRow title="AI-made picture signal">
          {det.status !== "checked" || detNothing ? (
            <>
              <Line quiet>Not checked</Line>
              {detWhy && <Line quiet>{detWhy}</Line>}
            </>
          ) : (
            <>
              {agreement && <Line raised={likelyAi}>{agreement}</Line>}
              {det.generated != null && <Meter value={det.generated} label={`${pct(det.generated)}% likely made by an AI image generator`} raised={likelyAi} />}
              {det.second_opinion != null && <Meter value={det.second_opinion} label={`Second detector: ${pct(det.second_opinion)}% likely AI-made`} raised={likelyAi} />}
              {det.face_swap != null ? (
                <>
                  <Meter value={det.face_swap} label={`${pct(det.face_swap)}% likely a face was swapped or changed by AI`} />
                  {det.faces != null && <Line quiet>{plural(det.faces, "1 face checked", "{n} faces checked")}</Line>}
                </>
              ) : (
                det.faces === 0 && <Line quiet>No face to check for a swap</Line>
              )}
              {det.voice != null && <Meter value={det.voice} label={`${pct(det.voice)}% likely a machine-made voice (experimental)`} />}
              <p className="pt-1 text-xs text-ink3">A detector&apos;s estimate, not a finding.</p>
              {det.on_server && <p className="text-xs text-ink3">This check ran on Factify&apos;s own server.</p>}
            </>
          )}
        </CheckRow>

        <CheckRow title="Editing signals">
          {edit.status !== "checked" ? (
            <Line quiet>Not checked</Line>
          ) : !edit.uneven_noise && !edit.spectral_peaks ? (
            <Line>No uneven noise or unusual patterns found</Line>
          ) : (
            <>
              {edit.uneven_noise && <Line raised>Parts of the picture have uneven noise, which editing can cause</Line>}
              {edit.spectral_peaks && <Line raised>Unusual patterns in the fine detail, which generators and heavy compression can cause</Line>}
            </>
          )}
        </CheckRow>
      </Box>
      {footnote && (
        <p className="mt-2.5 px-1 text-xs leading-relaxed text-ink3">
          These are checks of the picture itself. They never change the verdict, which rests only on cited sources, and a clean result doesn&apos;t
          prove a picture is real.
        </p>
      )}
    </>
  );
}

/** What was checked, for a case from before 1.8, which does not say what was read. */
function WhatWeChecked({ v, kind, submitted, preview }: { v: Verdict; kind: Kind; submitted?: string | null; preview?: string | null }) {
  const [whole, setWhole] = useState(false);
  const reading = v.image_reading ?? null;
  const video = v.media_report?.kind === "video";
  const nothing = nothingToCheck(v);
  const label =
    kind === "text"
      ? "Text"
      : kind === "link"
        ? `Link${submitted ? ` · ${host(submitted)}` : ""}`
        : kind === "pdf"
          ? "PDF"
          : kind === "post"
            ? "Post"
            : video
            ? "Video"
            : "Image";
  const fromPicture = kind === "image" && !!reading?.text?.trim();
  let quote = (
    kind === "text" ? (submitted ?? headlineOf(v) ?? "") : kind === "image" ? (fromPicture ? reading!.text!.replace(/\n\s*\n/g, "\n") : "") : (headlineOf(v) ?? "")
  ).trim();
  const limit = 600;
  const long = quote.length > limit;
  if (long && !whole) quote = quote.slice(0, limit);
  // Anchors are offsets into a message as it was sent; only a message's quote is that.
  const spans = nothing ? [] : spansIn(quote, v.claims, kind === "text" ? 0 : null);
  let said = v.speech?.text?.trim() ?? "";
  const saidLong = said.length > limit;
  if (saidLong && !whole) said = said.slice(0, limit);
  const saidSpans = said && !nothing ? spansIn(said, v.claims, null) : [];
  const keys = [...new Set([...spans, ...saidSpans].map((s) => s.mark))];

  return (
    <Box className="p-4 sm:p-5">
      <div className="flex items-center gap-2 text-xs font-semibold text-ink3">
        {preview && kind === "image" && !video && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={preview} alt="" className="h-6 w-6 rounded object-cover" />
        )}
        What we checked · {label}
      </div>
      {reading && kind !== "text" && (
        <>
          {(reading.kind || reading.publisher?.trim()) && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {reading.kind && <span className="rounded-full bg-sf2 px-2.5 py-0.5 text-xs font-medium text-ink2">{IMAGE_KIND[reading.kind] ?? "Picture"}</span>}
              {reading.publisher?.trim() && <span className="rounded-full bg-sf2 px-2.5 py-0.5 text-xs font-medium text-ink2">Shows: {reading.publisher.trim()}</span>}
            </div>
          )}
          {reading.description?.trim() && <p className="mt-2 text-sm leading-relaxed text-ink2">{reading.description}</p>}
          {fromPicture && quote && <div className="mt-3 text-xs font-semibold text-ink3">Text in the picture</div>}
        </>
      )}
      {quote ? (
        <div className="mt-2">
          <Underlined text={quote} spans={spans} cut={long && !whole} />
          {long && (
            <button type="button" onClick={() => setWhole(!whole)} className="mt-2 text-sm font-semibold text-acc-ink">
              {whole ? "Show less" : "Show all the text"}
            </button>
          )}
        </div>
      ) : (
        kind === "image" && reading && <p className="mt-2 text-xs text-ink3">We found no text in this picture, so we checked the picture itself.</p>
      )}
      {said && (
        <div className="mt-3">
          <div className="mb-2 text-xs font-semibold text-ink3">Said in the video</div>
          <Underlined text={said} spans={saidSpans} cut={saidLong && !whole} />
          {saidLong && !long && (
            <button type="button" onClick={() => setWhole(!whole)} className="mt-2 text-sm font-semibold text-acc-ink">
              {whole ? "Show less" : "Show all the text"}
            </button>
          )}
          {v.speech?.cut_off && <p className="mt-1.5 text-xs text-ink3">Only the first part of the video was heard.</p>}
        </div>
      )}
      <MarkKey marks={keys} />
    </Box>
  );
}

function MediaMatch({ e, preview }: { e: Evidence; preview?: string | null }) {
  const earlier = e.earlier_media ?? null;
  const published = earlier?.published_at ?? e.published_on ?? null;
  const similarity = earlier?.similarity ?? e.match_basis?.value ?? 0;
  const publisher = earlier?.publisher?.trim() || e.publisher || host(e.citation_url);
  // A post's picture is our own copy, gone after an hour: then the words stand in.
  const [mine, setMine] = useState(true);
  return (
    <Box className="mt-3 p-3">
      <div className="grid grid-cols-2 gap-2">
        <div>
          <div className="flex h-24 items-center justify-center overflow-hidden rounded-xl bg-sf2 text-[10px] tracking-widest text-ink3">
            {preview && mine ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={preview} alt="Your picture" onError={() => setMine(false)} className="h-full w-full object-cover" />
            ) : (
              "YOUR PICTURE"
            )}
          </div>
          <div className="mt-1.5 text-xs font-semibold text-ink">Your picture</div>
          <div className="text-xs text-ink3">Shared today</div>
        </div>
        <div>
          <div className="flex h-24 items-center justify-center overflow-hidden rounded-xl bg-mis-soft text-[10px] tracking-widest text-mis">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            {earlier?.thumbnail_url ? <img src={served(earlier.thumbnail_url)} alt="Earlier copy" className="h-full w-full object-cover" /> : "EARLIER COPY"}
          </div>
          <div className="mt-1.5 text-xs font-semibold text-ink">{published ? `Published ${day(published)}` : "EARLIER COPY"}</div>
          <div className="truncate text-xs text-ink3">{similarity > 0 ? `${publisher} · ${pct(similarity)}% visual match` : `${publisher} · earlier copy`}</div>
        </div>
      </div>
      <div className="mt-2.5 text-sm font-semibold text-mis">Matches a picture published earlier</div>
    </Box>
  );
}

function RightAndWrong({ claims }: { claims: Claim[] }) {
  return (
    <Box className="space-y-4 p-4">
      {ORDER.filter((m) => claims.some((c) => markOf(c) === m)).map((m) => (
        <div key={m}>
          <div className={`text-sm font-bold ${MARK[m].tone}`}>{MARK[m].group}</div>
          {claims
            .filter((c) => markOf(c) === m)
            .map((c) => {
              const smaller = m === "partly" ? c.evidence.find((e) => e.direction === "contextualizes" && isNarrower(e)) : undefined;
              return (
                <div key={c.id} className="mt-1.5 pl-1">
                  <p className="text-sm leading-snug text-ink">{c.text}</p>
                  {c.in_full && <p className="text-xs text-ink3">In full: {c.in_full}</p>}
                  {smaller?.source_excerpt?.trim() && (
                    <div className="mt-1.5 rounded-xl bg-mis-soft px-3 py-2">
                      <div className="text-xs font-semibold text-ink3">What sources actually report</div>
                      <p className="font-medium tracking-tight mt-0.5 line-clamp-5 text-sm text-ink">&ldquo;{smaller.source_excerpt.trim()}&rdquo;</p>
                      <div className="mt-0.5 text-xs font-semibold text-ink2">— {smaller.publisher || host(smaller.citation_url)}</div>
                    </div>
                  )}
                </div>
              );
            })}
        </div>
      ))}
    </Box>
  );
}

function SourceCard({ e }: { e: Evidence }) {
  const tone = e.direction === "contradicts" ? "text-false bg-false-soft" : e.direction === "supports" ? "text-true bg-true-soft" : "text-mis bg-mis-soft";
  const word = e.direction === "contradicts" ? "Refutes" : e.direction === "supports" ? "Supports" : "Context";
  const tier = { A: "Signed content credential", B: "Dated source", C: "Published fact-check" }[e.tier] ?? "Corroboration";
  const cred = e.credibility === "HIGH" ? "Highly credible" : e.credibility === "MEDIUM" ? "Credible" : "Source";
  const meta = [cred, day(e.published_on)].filter(Boolean).join(" · ");
  return (
    <a
      href={e.citation_url}
      target="_blank"
      rel="noopener noreferrer"
      className="flex flex-col rounded-[12px] border border-line bg-sf p-4 shadow-card transition hover:border-acc-ink/40"
    >
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <div className="truncate font-semibold text-ink">{e.publisher || host(e.citation_url)}</div>
          <div className="truncate text-xs text-ink3">{tier}</div>
        </div>
        <span className={`shrink-0 rounded-lg px-2 py-0.5 text-xs font-bold ${tone}`}>{word}</span>
      </div>
      {e.source_excerpt?.trim() && <p className="font-medium tracking-tight mt-2.5 line-clamp-4 text-[15px] leading-snug text-ink">&ldquo;{e.source_excerpt.trim()}&rdquo;</p>}
      <div className="mt-auto flex items-center justify-between gap-2 pt-3 text-xs">
        <span className="truncate text-ink3">{meta}</span>
        <span className="shrink-0 font-semibold text-acc-ink">Read →</span>
      </div>
    </a>
  );
}

/** In place of the verdict when it was held back for what could not be read: nothing
 * checkable was read, what was read held no claim, or (where the server holds back on
 * any blocking gap) what was missed could decide it. The ways on: send what was missed
 * (the text, the picture, the video), or check only what was read. */
function Withheld({ read, onCheckRead, onSend }: { read: InputRead; onCheckRead?: () => void; onSend?: (what: "text" | "file") => void }) {
  // Checking "what was read" changes the answer only when what was missed could decide
  // it and something checkable was read; otherwise it would be held back again.
  const partial = readEnough(read) && blocked(read) ? onCheckRead : undefined;
  // An upload was the picture or video already: sending it again reads it no further,
  // so its text, or what was read of it, is the way on.
  const upload = read.kind === "image" || read.kind === "video" || read.kind === "pdf";
  // What the gaps call for first - the picture or video itself, or the text - is the
  // main action. Nobody can upload a video from YouTube: its words are the way on.
  const youtube = (read.platform ?? "").toLowerCase() === "youtube";
  const main = upload ? (partial ? "read" : "text") : !youtube && missedMedia(read) ? "file" : "text";
  const noun = readNoun(read);
  const send = upload ? "Paste its text" : `Send the ${main === "file" ? "picture or video" : "text"} itself`;
  return (
    <div className="rounded-[14px] border border-line2 bg-linear-to-b from-unc-soft via-sf to-sf p-5 shadow-card sm:p-6">
      <div className="font-mono text-[11px] tracking-[0.14em] text-unc">NO VERDICT</div>
      <div className="mt-1 text-[2.1rem] leading-none font-medium tracking-tight text-unc sm:text-[2.4rem]">Not checked yet</div>
      <p className="mt-3 text-[15px] font-semibold text-ink">
        {readAny(read) ? "Factify could not read all of this, so it has not given a verdict." : `Factify couldn't read this ${noun}, so it has not given a verdict.`}
      </p>
      <p className="mt-1.5 text-[15px] leading-relaxed text-ink2">
        {readAny(read) ? "What it read and what it couldn't are below." : "The reason is below."} {send} and Factify will check all of it
        {partial ? `, or check only what it could read of this ${noun}.` : "."}
      </p>
      <div className="mt-4 flex flex-wrap gap-2">
        {onSend && (
          <>
            <Button type="button" variant={main === "text" ? "primary" : "outline"} onClick={() => onSend("text")}>
              Paste the text
            </Button>
            <Button type="button" variant={main === "file" ? "primary" : "outline"} onClick={() => onSend("file")}>
              Upload the picture or video
            </Button>
          </>
        )}
        {partial && (
          <Button type="button" variant={main === "read" ? "primary" : "outline"} onClick={partial}>
            Check what was read
          </Button>
        )}
      </div>
      {partial && (
        <p className="mt-2.5 text-xs leading-relaxed text-ink3">
          Checking what was read gives an answer about that part only. It is never &ldquo;True&rdquo;, because what wasn&apos;t read could say otherwise.
        </p>
      )}
    </div>
  );
}

type Kind = "text" | "link" | "post" | "image" | "pdf";

function kindOf(v: Verdict, given?: string | null): Kind {
  // What was read says best what it was: a link sent to be checked may be a post.
  const read = v.input_read?.kind;
  if (read === "social_post") return "post";
  if (read === "text" || read === "link" || read === "pdf" || read === "image") return read;
  if (read === "video") return "image";
  if (given === "text" || given === "link" || given === "pdf" || given === "image") return given;
  // A video is shown from its frames, as a picture is.
  if (given === "video") return "image";
  if (v.media_report || v.image_reading) return "image";
  return "text";
}

// ---------------------------------------------------------------- the result

export function Result({
  result: v,
  kind: givenKind,
  submitted,
  preview,
  onCheckRead,
  onSend,
}: {
  result: Verdict;
  kind?: string | null;
  submitted?: string | null;
  preview?: string | null;
  // "Check what was read": the same input sent again, checked past what could not be
  // read. Left out where it cannot be sent again (a file, opened from History).
  onCheckRead?: () => void;
  // Back to the box, to paste the text or upload the picture or video instead.
  onSend?: (what: "text" | "file") => void;
}) {
  const read = v.input_read ?? null;
  const withheld = withheldOf(v);
  const partly = partlyReadOf(v);
  const nothing = nothingToCheck(v);
  const decided = v.verdict !== "UNCONFIRMED";
  const style = nothing ? NOTHING : (VERDICT[v.verdict] ?? VERDICT.UNCONFIRMED);
  const kind = kindOf(v, givenKind);
  const video = v.media_report?.kind === "video";
  // What the input is called; a case stored before 1.8 says it by what was sent.
  const noun = read ? readNoun(read) : { text: "message", link: "page", post: "post", image: video ? "video" : "picture", pdf: "PDF" }[kind];
  // Nothing it says was searched for: no "no source was found" about it.
  const unsearched = !decided && !nothing && extractionFailed(v);
  // Checked from part of the input with all of that part supported: unconfirmed
  // because of what was not read, never because the news is too recent.
  const supportedPart = partlySupported(v);
  const line = supportedPart ? "Supported as far as it could be read" : v.action === "WAIT_AND_RECHECK" ? "Too recent to confirm yet" : style.line;
  const summary = decided
    ? v.summary || v.action_reason
    : supportedPart
      ? `Everything Factify could read is supported by sources, but part of this ${noun} couldn't be read, and that part could say otherwise. So it isn't called true.`
      : unsearched
        ? `Factify couldn't pick out the claims in this ${noun} this time, so what it says wasn't checked against any source. That says nothing about whether it's true. Check it again in a little while.`
        : nothing
        ? read?.kind === "social_post" || read?.kind === "link"
          ? `We read this ${noun} and found no claim in it that can be checked - no news, figure or announcement. There's nothing here to confirm or rule out.`
          : video
            ? "We checked this video's frames and found no claim in them that can be checked - no news, figure or announcement. There's nothing here to confirm or rule out."
            : v.image_reading
              ? "We read this picture and found no claim in it that can be checked - no news, figure or announcement, just an image. There's nothing here to confirm or rule out."
              : "We didn't find a factual claim in this - it reads as opinion, a joke or conversation, so there's nothing here to confirm or rule out."
        : UNCONFIRMED_BODY;
  const incomplete = incompleteLine(v);
  // A post's pictures, in order, from our own copies; an upload's is the person's own.
  const shots = [...new Set((read?.parts ?? []).flatMap((p) => (p.media_url ? [served(p.media_url)] : [])))];
  const previewOf = (i: number) => (i === 0 && preview) || shots[i] || null;
  const reports = v.media_report ? [v.media_report, ...(v.media_reports ?? [])] : [];
  const note = aiNote(v);
  const searchUnavailable = v.claims.some((c) => c.search === "unavailable");
  const claims = nothing ? [] : v.claims.filter((c) => c.claim_type !== "MEDIA" || decisive(c));
  const sources = sourcesOf(v);
  const media = v.claims.flatMap((c) => c.evidence).find(isMediaMatch);
  const technique = decided ? techniqueOf(v) : null;
  const decidedMarks = new Set(claims.filter((c) => markOf(c) !== "unconfirmed").map(markOf));
  const mixed = claims.length > 0 && (v.verdict === "PARTLY_TRUE" || decidedMarks.size >= 2 || decidedMarks.has("partly"));
  const statusNote = ORDER.filter((m) => claims.some((c) => markOf(c) === m))
    .map((m) => `${claims.filter((c) => markOf(c) === m).length} ${MARK[m].state.toLowerCase()}`)
    .join(" · ");

  const [correction, setCorrection] = useState<"idle" | "busy" | "copied" | "failed">("idle");
  const [report, setReport] = useState<"idle" | "busy" | "done" | "failed">("idle");

  async function copyCorrection() {
    setCorrection("busy");
    try {
      const r = await api<{ message: string }>(`/v1/cases/${v.case_id}/correction-text`, { method: "POST", json: { language: correctionLanguage(v) } });
      await navigator.clipboard.writeText(r.message);
      setCorrection("copied");
    } catch {
      setCorrection("failed");
    }
  }
  async function sendReport() {
    setReport("busy");
    try {
      await api(`/v1/cases/${v.case_id}/report`, { method: "POST" });
      setReport("done");
    } catch {
      setReport("failed");
    }
  }

  const shareWord = v.verdict === "TRUE" ? "Share result" : v.verdict === "MISLEADING" ? "Share with context" : "Share correction";

  return (
    <div>
      {withheld && read ? (
        <Withheld read={read} onCheckRead={onCheckRead} onSend={onSend} />
      ) : (
        // The verdict.
        <div className={`rounded-[14px] border border-line2 bg-linear-to-b ${style.grad} via-sf to-sf p-5 shadow-card sm:p-6`}>
          <div className={`font-mono text-[11px] tracking-[0.14em] ${style.tone}`}>VERDICT</div>
          <div className="mt-1 flex flex-wrap items-end justify-between gap-x-4 gap-y-2">
            <span className={`leading-none font-medium tracking-tight ${style.tone} ${nothing || !decided ? "text-[2.1rem] sm:text-[2.4rem]" : "text-[2.4rem] sm:text-[2.75rem]"}`}>{style.word}</span>
            {decided && v.confidence != null && <span className={`rounded-md px-2 py-0.5 text-xs font-medium ${style.soft} ${style.tone}`}>{v.confidence}% confidence</span>}
          </div>
          <p className="mt-3 text-[15px] font-semibold text-ink">{line}</p>
          <p className="mt-1.5 text-[15px] leading-relaxed text-ink2">{summary}</p>
          {note && <p className="mt-2.5 text-[15px] font-semibold text-ink">{note}</p>}
          {(v.from_cache || partly) && (
            <div className="mt-3 flex flex-wrap gap-2">
              {partly && <span className="inline-flex rounded-md bg-mis-soft px-2 py-0.5 text-xs font-medium text-mis">Checked from part of the {noun}</span>}
              {v.from_cache && (
                <span className="inline-flex rounded-md bg-hover px-2 py-0.5 text-xs font-medium text-ink2">
                  Checked earlier · reused from {day(v.retrieved_at, false) ?? "an earlier check"}
                </span>
              )}
            </div>
          )}
          {searchUnavailable ? (
            <p className="mt-3 rounded-[10px] bg-hover px-3 py-2.5 text-sm text-ink2">
              Our news search couldn&apos;t be reached, so this wasn&apos;t checked against news reports. Check it again in a little while.
            </p>
          ) : (
            incomplete && <p className="mt-3 rounded-[10px] bg-hover px-3 py-2.5 text-sm text-ink2">{incomplete}</p>
          )}
          {!nothing && (
            <div className="mt-4 flex flex-wrap gap-2">
              {decided && (
                <button
                  type="button"
                  onClick={copyCorrection}
                  disabled={correction === "busy"}
                  className="rounded-[9px] bg-acc px-4 py-2 text-sm font-medium text-on-acc transition-colors hover:bg-acc-h disabled:opacity-60"
                >
                  {correction === "copied" ? "Copied - paste it in the chat" : correction === "busy" ? "Preparing…" : shareWord}
                </button>
              )}
              {correction === "failed" && <span className="self-center text-sm text-false">Couldn&apos;t prepare the message. Try again.</span>}
            </div>
          )}
        </div>
      )}

      <div className="mt-4">
        {read ? (
          <WhatWeRead read={read} claims={v.claims} nothing={nothing} preview={preview} picture={v.image_reading} />
        ) : (
          <WhatWeChecked v={v} kind={kind} submitted={submitted} preview={preview} />
        )}
      </div>

      {/* About the site a link is on; a post's site is the platform, which says nothing. */}
      {v.source_profile && !read?.platform && (
        <>
          <Section title="About this website" note="Not part of the verdict" />
          <Box className="p-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-semibold text-ink">{v.source_profile.domain}</span>
              <span
                className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                  v.source_profile.trusted ? "bg-true-soft text-true" : v.source_profile.level === "HIGH" || v.source_profile.level === "MEDIUM" ? "bg-mis-soft text-mis" : "bg-unc-soft text-unc"
                }`}
              >
                {v.source_profile.fact_checker ? "Fact-checker" : v.source_profile.trusted ? `Trusted · ${v.source_profile.trust}` : "Not on our trusted list"}
              </span>
            </div>
            <ul className="mt-2 space-y-1 text-sm text-ink2">
              {(v.source_profile.findings ?? []).map((f) => (
                <li key={f}>{f}</li>
              ))}
              {(v.source_profile.warnings ?? []).map((w) => (
                <li key={w} className="font-semibold text-mis">
                  {w}
                </li>
              ))}
            </ul>
            <p className="mt-2 text-xs text-ink3">What we know about the site itself. It never makes a claim true or false.</p>
          </Box>
        </>
      )}

      {v.recurrence?.summary && (v.recurrence.times_seen ?? 0) > 0 && (
        <Box className="mt-4 p-4">
          <div className="text-xs font-semibold text-ink3">Seen before</div>
          <p className="mt-1 text-sm text-ink2">{v.recurrence.summary}</p>
        </Box>
      )}

      {mixed && (
        <>
          <Section title="What's right, what's wrong" />
          <RightAndWrong claims={claims} />
        </>
      )}

      {media && v.verdict !== "TRUE" && <MediaMatch e={media} preview={previewOf(0)} />}

      {v.media_report && (
        <>
          <Section
            title={video ? "Video checks" : "Picture checks"}
            note={v.media_report.frames != null ? `${plural(v.media_report.frames, "1 still frame", "{n} still frames")} · Not part of the verdict` : "Not part of the verdict"}
          />
          {reports.length > 1 ? (
            // A post's pictures, each checked on its own, in the post's order.
            <div className="space-y-4">
              {reports.map((r, i) => (
                <div key={i}>
                  <div className="mb-2 flex items-center gap-2 px-1 text-sm font-medium text-ink">
                    {previewOf(i) && (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={previewOf(i)!} alt="" className="h-6 w-6 rounded object-cover" onError={(e) => (e.currentTarget.style.display = "none")} />
                    )}
                    Picture {i + 1} of {reports.length}
                  </div>
                  <PictureChecks report={r} preview={previewOf(i)} footnote={i === reports.length - 1} />
                </div>
              ))}
            </div>
          ) : (
            <PictureChecks report={v.media_report} preview={previewOf(0)} />
          )}
        </>
      )}

      {claims.length > 0 && (
        <>
          <Section title={plural(claims.length, "1 claim", "{n} claims")} note={statusNote} />
          <Box className="divide-y divide-line">
            {claims.map((c) => {
              const m = markOf(c);
              return (
                <div key={c.id} className="flex gap-3 px-4 py-3.5">
                  <span className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full ${MARK[m].tone.replace("text-", "bg-")}`} />
                  <div className="min-w-0">
                    <p className="font-medium leading-snug text-ink">{c.text}</p>
                    {c.in_full && <p className="text-xs text-ink3">In full: {c.in_full}</p>}
                    <p className="mt-1 text-sm leading-relaxed text-ink3">
                      <span className={`font-semibold ${MARK[m].tone}`}>{MARK[m].state}. </span>
                      {claimReason(c)}
                    </p>
                  </div>
                </div>
              );
            })}
          </Box>
        </>
      )}

      {technique && (
        <div className="mt-4 rounded-[14px] bg-mis-soft p-4">
          <div className="font-mono text-[11px] tracking-[0.12em] text-mis">HOW POSTS LIKE THIS MISLEAD</div>
          <div className="font-medium tracking-tight mt-1 text-xl text-ink">{technique[0]}</div>
          <p className="mt-1 text-sm leading-relaxed text-ink2">{technique[1]}</p>
        </div>
      )}

      {sources.length > 0 ? (
        <>
          <Section title="Sources" note="Opens the page it was quoted from" />
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {sources.map((e) => (
              <SourceCard key={e.id} e={e} />
            ))}
          </div>
        </>
      ) : (
        !decided &&
        !nothing &&
        !withheld &&
        !unsearched && (
          <>
            <Box className="mt-4 p-4">
              <div className="font-semibold text-ink">No citable source was found</div>
              <p className="mt-1 text-sm leading-relaxed text-ink2">
                This does not mean the content is false. It means nothing we could cite either supports or contradicts it, so Factify did not decide.
              </p>
            </Box>
            <Section title="What Factify cannot establish" />
            <Box className="divide-y divide-line text-sm leading-relaxed text-ink2">
              <p className="px-4 py-3">Whether something unreported is false. Absence of coverage is not evidence either way.</p>
              <p className="px-4 py-3">Anything about private content, or claims no published source has addressed.</p>
              <p className="px-4 py-3">Intent. We can show what a source said and when, not why someone shared it.</p>
            </Box>
          </>
        )
      )}

      {v.receipt?.receipt_id && (
        <div className="mt-4 rounded-[14px] border border-dashed border-line2 px-4 py-3 text-sm">
          {v.receipt.verified ? (
            <>
              <div className="font-semibold text-ink">Receipt verified</div>
              <div className="text-xs text-ink3">The evidence is unchanged since it was signed</div>
            </>
          ) : (
            <>
              <div className="font-semibold text-false">Receipt did not verify</div>
              <div className="text-xs text-ink3">The stored evidence no longer matches what was signed</div>
            </>
          )}
        </div>
      )}

      <div className="mt-5 flex flex-wrap items-center justify-between gap-2 px-1 text-xs text-ink3">
        <span>
          Checked{" "}
          {v.retrieved_at
            ? new Date(v.retrieved_at).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" })
            : "just now"}
        </span>
        {/* Nothing was decided, so there is no result to call wrong. */}
        {!withheld && (
          <button type="button" onClick={sendReport} disabled={report === "busy" || report === "done"} className="font-semibold text-ink2 hover:text-ink disabled:opacity-70">
            {report === "done" ? "Reported. We'll take another look at this result." : report === "busy" ? "Reporting…" : report === "failed" ? "Couldn't send. Try again" : "Report wrong result"}
          </button>
        )}
      </div>
    </div>
  );
}
