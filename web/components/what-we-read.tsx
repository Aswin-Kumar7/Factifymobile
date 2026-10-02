"use client";

// "What Factify read": the input as it was read, part by part, and what could not be
// read (contract 1.8, `input_read`). It replaces "What we checked", in the same place.
//
// A post, a page or a video can be read only in part: a caption cut at "… more", a
// page that gives its headline only, a video whose speech could not be heard. An
// answer about half a post used to read exactly like one about all of it. This panel
// shows what the answer rests on - the post's text, the words in each picture, what
// was said in the video - with each claim underlined where it was found, and says
// plainly what was missed. A description of what a picture or a video shows that no
// claim was looked for in (`checked: false`) is shown muted and marked as not checked:
// context, never evidence.
//
// Built to the same contract as the phone app's panel (design_plan.md section 7), in
// the app's English. A case stored before 1.8 has no reading; result.tsx then shows
// what it checked as it always did.

import { useState } from "react";
import type { Claim } from "@/components/result";

// ---------------------------------------------------------------- the reading (1.8)

export type ReadPart = {
  // message | post_text | quoted_post | title | description | article | linked_article |
  // picture_text | picture_description | transcript | on_screen_text |
  // video_description | document_text
  kind: string;
  label?: string | null;
  text: string;
  // False for a description of what a picture or a video shows: shown, never checked.
  checked: boolean;
  route: string;
  complete?: boolean;
  note?: string | null;
  // /v1/media/thumbnails/<key>: our own copy, kept for an hour; hidden once it is gone.
  media_url?: string | null;
  // Where this part sits in the text claims were found in (the input_anchor space),
  // counted in characters as the server counts them: code points, not UTF-16 units.
  char_start?: number | null;
  char_end?: number | null;
  seconds_read?: number | null;
  seconds_total?: number | null;
  language?: string | null;
};

export type ReadGap = { part: string; code: string; detail: string; blocking: boolean };

export type InputRead = {
  kind: "text" | "link" | "social_post" | "image" | "pdf" | "video" | string;
  platform?: string | null;
  url?: string | null;
  author?: string | null;
  handle?: string | null;
  published_at?: string | null;
  parts?: ReadPart[];
  gaps?: ReadGap[];
  limits?: string[];
  complete?: boolean;
  verdict_withheld?: boolean;
  checked_partially?: boolean;
};

// The reason the server gives a case checked from part of its input whose readable
// part is all supported (app/verdict/engine.py PARTLY_READ_REASON). That case is
// "wait and re-check", like news too recent to confirm, and must never be called so.
export const PARTLY_READ_REASON = "What could be read is supported; part of the input could not be read.";

const PLATFORM: Record<string, string> = { x: "X", instagram: "Instagram", youtube: "YouTube", facebook: "Facebook" };

export function platformName(platform: string | null | undefined): string | null {
  if (!platform) return null;
  return PLATFORM[platform.toLowerCase()] ?? platform;
}

/** What the input is called in a sentence: "part of this post", "this page". */
export function readNoun(read: InputRead | null | undefined): string {
  switch (read?.kind) {
    case "social_post":
      // A YouTube link is a video to the person who sent it, not a post.
      return read.platform === "youtube" ? "video" : "post";
    case "link":
      return "page";
    case "video":
      return "video";
    case "image":
      return "picture";
    case "pdf":
      return "PDF";
    case "text":
      return "message";
    default:
      return "input";
  }
}

const words = (text: string) => text.split(/\s+/).filter(Boolean).length;

// What Factify says a picture or a video shows. The server never counts it as read
// enough to check (CONTEXT_ONLY in app/extraction/reading.py), even where an upload's
// description is `checked` because claims were also looked for in it.
const DESCRIBED = new Set(["picture_description", "video_description"]);

/** Enough was read to check anything (Reading.substantive on the server): a checked
 * part of three words or more, or a picture read in full, which can still be checked
 * for where it appeared before. "Check what was read" is offered only then: with
 * nothing read, checking it again would only be held back again. */
export function readEnough(read: InputRead): boolean {
  return (read.parts ?? []).some((p) => p.kind === "picture_text" || (p.checked !== false && !DESCRIBED.has(p.kind) && words(p.text ?? "") >= 3));
}

/** 75 → "1:15"; 3725 → "1:02:05". */
export function clock(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const pad = (n: number) => String(n).padStart(2, "0");
  return h ? `${h}:${pad(m)}:${pad(s % 60)}` : `${m}:${pad(s % 60)}`;
}

// What each gap is called, by its code, as the app words it. A code this page does not
// know falls back to the server's own English sentence.
const GAP: Record<string, string> = {
  headline_only: "Only the headline and summary could be read. The rest is behind a sign-in, a consent page or a script.",
  text_truncated: "The post's text was cut short, so only its opening was read.",
  post_unavailable: "The post has been deleted, is private, or is a story, so it couldn't be read.",
  login_required: "The platform shows this only to people who are signed in.",
  not_supported: "Factify can't read posts from this platform yet. Paste the text or upload a screenshot.",
  picture_unread: "A picture in it couldn't be read.",
  video_unread: "The video couldn't be downloaded or watched.",
  speech_unread: "What is said in the video couldn't be heard.",
  cut_off: "Reading stopped before the end, so only part of it was read.",
  pages_unread: "Only the first pages of the PDF were read.",
  too_large: "The video is too large to download, even at its lowest quality.",
  needs_background: "Videos are read only in a full check, not a quick one.",
  reader_unavailable: "A reader this needs isn't available right now.",
  first_picture_only: "Only the first picture of the album could be seen.",
  article_truncated: "The article is long; its opening was read.",
  description_unread: "The video's description couldn't be read.",
  linked_page_unread: "The article it links to gave only its headline, so it was left out.",
};

// Where one code covers different things, by the part it is about (`gap.part`).
// "cut_off" is a video longer than is read, speech heard only in part, the words on
// some of its frames, or a picture or PDF with more text than is read at once.
const BY_PART: Record<string, Record<string, string>> = {
  cut_off: {
    video: "Only the start of the video was watched. What is shown or said after that wasn't checked.",
    transcript: "Only the start of what is said in the video was heard.",
    on_screen_text: "Not every word shown in the video could be read in time.",
    picture_text: "The picture holds more text than is read at once. Only its start was checked.",
    document_text: "The PDF holds more text than is read at once. Only its start was checked.",
  },
  reader_unavailable: {
    post: "Factify couldn't read this post this time.",
    video: "Factify can't watch this video, so what is said and shown in it wasn't read.",
    transcript: "Factify can't listen to this video, so what is said in it wasn't read.",
    picture_text: "Reading the words in pictures isn't available right now.",
    on_screen_text: "Reading the words shown in videos isn't available right now.",
  },
};

function gapLine(gap: ReadGap, parts: ReadPart[]): string {
  if (gap.code === "cut_off") {
    // Speech heard only in part says how much: the "{read} of {total}" the app shows.
    const heard = parts.find((p) => p.kind === gap.part && p.seconds_read != null);
    if (heard?.seconds_read != null && heard.seconds_total != null && heard.seconds_total > heard.seconds_read) {
      return `Only the first ${clock(heard.seconds_read)} of the ${clock(heard.seconds_total)} video was heard and read.`;
    }
  }
  return BY_PART[gap.code]?.[gap.part] ?? GAP[gap.code] ?? ((gap.detail ?? "").trim() || "Part of it couldn't be read.");
}

// Gaps the full picture or video would fill: then uploading it is the first thing to try.
const MEDIA_GAPS = new Set(["picture_unread", "video_unread", "speech_unread", "too_large", "needs_background", "first_picture_only"]);
// The parts of a picture or a video: a gap in one of these, whatever its code, is too.
const MEDIA_PARTS = new Set(["video", "transcript", "on_screen_text", "picture_text"]);

/** Whether sending the picture or video itself is the way to fill what was missed. */
export function missedMedia(read: InputRead): boolean {
  return (read.gaps ?? []).some((g) => MEDIA_GAPS.has(g.code) || ((g.code === "cut_off" || g.code === "reader_unavailable") && MEDIA_PARTS.has(g.part)));
}

// ---------------------------------------------------------------- where claims are

export type Mark = "wrong" | "partly" | "context" | "right" | "unconfirmed";
export const MARK: Record<Mark, { state: string; group: string; tone: string; soft: string }> = {
  wrong: { state: "Contradicted", group: "Wrong", tone: "text-false", soft: "bg-false-soft" },
  partly: { state: "Partly true", group: "Only partly right", tone: "text-mis", soft: "bg-mis-soft" },
  context: { state: "Missing context", group: "Missing context", tone: "text-mis", soft: "bg-mis-soft" },
  right: { state: "Supported", group: "Right", tone: "text-true", soft: "bg-true-soft" },
  unconfirmed: { state: "Unconfirmed", group: "Not confirmed", tone: "text-unc", soft: "bg-unc-soft" },
};

export function markOf(c: Claim): Mark {
  if (c.status === "SUPPORTED") return "right";
  if (c.status === "CONTRADICTED") return "wrong";
  if (c.status === "MISLEADING_CONTEXT") return c.rule_id === "rule.narrower_scope" ? "partly" : "context";
  return "unconfirmed";
}

export type Span = { start: number; end: number; mark: Mark };

/** A server offset - counted in code points, as Python counts - as an index into a
 * JavaScript string, which counts an emoji as two. Without it every claim after an
 * emoji in a post is underlined one character off per emoji. */
function utf16(text: string, points: number): number | null {
  let at = 0;
  for (let n = 0; n < points; n++) {
    if (at >= text.length) return null;
    at += (text.codePointAt(at) ?? 0) > 0xffff ? 2 : 1;
  }
  return at;
}

function anchorOf(c: Claim): { start: number; end: number } | null {
  const a = c.input_anchor ?? c.evidence.find((e) => e.input_anchor?.char_start != null)?.input_anchor;
  if (a?.char_start == null || a.char_end == null || a.char_start < 0 || a.char_start >= a.char_end) return null;
  return { start: a.char_start, end: a.char_end };
}

const plain = (s: string) =>
  s
    .toLowerCase()
    .replace(/\s+/g, " ")
    .replace(/[.!?।]+$/, "")
    .trim();

/** Where a claim's words are in a text, when no anchor says: the whole claim, else the
 * longest run of four or more of its words. */
function matchIn(text: string, claim: string): [number, number] | null {
  const lower = text.toLowerCase();
  const needle = plain(claim);
  const at = needle.length >= 8 ? lower.indexOf(needle) : -1;
  if (at >= 0) return [at, at + needle.length];
  const list = needle.split(" ").filter(Boolean);
  for (let len = list.length - 1; len >= 4; len--) {
    for (let s = 0; s + len <= list.length; s++) {
      const frag = list.slice(s, s + len).join(" ");
      const found = lower.indexOf(frag);
      if (found >= 0) return [found, found + frag.length];
    }
  }
  return null;
}

function add(list: Span[], span: Span) {
  if (!list.some((f) => span.start < f.end && f.start < span.end)) list.push(span);
}

/** Where each claim sits in one quoted text (a case from before 1.8). Anchors are used
 * only when `base` says the text starts at that offset of the anchors' space. */
export function spansIn(text: string, claims: Claim[], base: number | null): Span[] {
  if (!text) return [];
  const found: Span[] = [];
  for (const c of claims) {
    if (c.claim_type === "MEDIA") continue;
    const a = base != null ? anchorOf(c) : null;
    const start = a ? utf16(text, a.start - base!) : null;
    const end = a ? utf16(text, a.end - base!) : null;
    const span: [number, number] | null = start != null && end != null && start < end ? [start, end] : matchIn(text, c.text);
    if (span) add(found, { start: span[0], end: span[1], mark: markOf(c) });
  }
  return found.sort((x, y) => x.start - y.start);
}

/** Each claim underlined once, in the part its anchor falls in; a claim with no anchor
 * that lands in a part is found by its words, in the first part that has them. A
 * picture's or a video's own claim (MEDIA) is underlined only where an anchor puts it:
 * its words are Factify's, not the post's. */
function spansByPart(parts: ReadPart[], claims: Claim[]): Span[][] {
  const out: Span[][] = parts.map(() => []);
  const placed = new Set<string>();
  for (const c of claims) {
    const a = anchorOf(c);
    if (!a) continue;
    const i = parts.findIndex((p) => p.checked && p.char_start != null && p.char_end != null && p.char_start <= a.start && a.end <= p.char_end);
    if (i < 0) continue;
    const p = parts[i];
    const start = utf16(p.text, a.start - p.char_start!);
    const end = utf16(p.text, a.end - p.char_start!);
    if (start == null || end == null || start >= end) continue;
    add(out[i], { start, end, mark: markOf(c) });
    placed.add(c.id);
  }
  for (const c of claims) {
    if (placed.has(c.id) || c.claim_type === "MEDIA") continue;
    for (let i = 0; i < parts.length; i++) {
      if (!parts[i].checked) continue;
      const span = matchIn(parts[i].text, c.text);
      if (span) {
        add(out[i], { start: span[0], end: span[1], mark: markOf(c) });
        break;
      }
    }
  }
  return out.map((list) => list.sort((x, y) => x.start - y.start));
}

const UNDERLINE: Record<Mark, string> = {
  wrong: "decoration-false bg-false-soft",
  partly: "decoration-mis bg-mis-soft",
  context: "decoration-mis bg-mis-soft",
  right: "decoration-true bg-true-soft",
  unconfirmed: "decoration-unc bg-unc-soft",
};

/** The text with its claims underlined in their colours; the spans past `upTo` are cut. */
function marked(text: string, spans: Span[], upTo = text.length): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  let at = 0;
  spans.forEach((s, i) => {
    if (s.start >= upTo) return;
    if (s.start > at) nodes.push(text.slice(at, s.start));
    nodes.push(
      <span key={i} className={`underline decoration-2 underline-offset-4 ${UNDERLINE[s.mark]}`}>
        {text.slice(s.start, Math.min(s.end, upTo))}
      </span>,
    );
    at = Math.min(s.end, upTo);
  });
  if (at < upTo) nodes.push(text.slice(at, upTo));
  return nodes;
}

/** A quote, underlined: how a case from before 1.8 shows what it checked. */
export function Underlined({ text, spans, cut }: { text: string; spans: Span[]; cut: boolean }) {
  return (
    <p className="font-medium tracking-tight whitespace-pre-line text-[17px] leading-relaxed text-ink">
      &ldquo;{marked(text, spans)}
      {cut ? "…" : ""}&rdquo;
    </p>
  );
}

/** Which colour is which, for the marks on show. */
export function MarkKey({ marks }: { marks: Mark[] }) {
  if (!marks.length) return null;
  return (
    <div className="mt-3 flex flex-wrap gap-x-3 gap-y-1">
      {marks.map((m) => (
        <span key={m} className="inline-flex items-center gap-1.5 text-xs text-ink3">
          <span className={`inline-block h-0.5 w-3.5 rounded ${MARK[m].tone.replace("text-", "bg-")}`} />
          {MARK[m].state}
        </span>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------- shared bits

// The server's own copies of pictures are under /v1; the browser reaches them through
// the signed-in proxy, as it does every other call.
export function served(url: string) {
  return url.startsWith("/v1/") ? `/api/f${url}` : url;
}

export function host(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export function day(value: string | null | undefined, withYear = true) {
  if (!value) return null;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString("en-IN", withYear ? { day: "numeric", month: "short", year: "numeric" } : { day: "numeric", month: "short" });
}

/** A picture from our own store, gone once its hour is up: then nothing is shown. */
function Thumb({ src, alt }: { src: string; alt: string }) {
  const [gone, setGone] = useState(false);
  if (gone) return null;
  return (
    <a href={src} target="_blank" rel="noopener noreferrer" className="shrink-0" aria-label={`${alt} (opens the picture)`}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={src} alt={alt} onError={() => setGone(true)} className="h-16 w-16 rounded-lg border border-line bg-sf2 object-cover" />
    </a>
  );
}

// ---------------------------------------------------------------- the panel

// A part's label when the server sent none; the server's labels are already this
// English ("Text in picture 1 of 2", "Said in the video").
const KIND_LABEL: Record<string, string> = {
  message: "Message",
  post_text: "Post",
  quoted_post: "Quoted post",
  title: "Title",
  description: "Description",
  article: "Article",
  linked_article: "Linked article",
  picture_text: "Text in the picture",
  picture_description: "What the picture shows",
  transcript: "Said in the video",
  on_screen_text: "Text shown in the video",
  video_description: "What the video shows",
  document_text: "Text in the PDF",
};

function labelOf(part: ReadPart): string {
  // The post's own label repeats who posted it, where and when: the header says that.
  if (part.kind === "post_text") return "Post";
  return part.label?.trim() || KIND_LABEL[part.kind] || "Read";
}

/** "6:52 heard", or "10:00 of 14:02 heard" when only part of it was. */
function heard(part: ReadPart): string | null {
  if (part.seconds_read == null) return null;
  if (part.seconds_total != null && part.seconds_total > part.seconds_read) return `${clock(part.seconds_read)} of ${clock(part.seconds_total)} heard`;
  return `${clock(part.seconds_read)} heard`;
}

// A long part is cut here until the person asks for all of it, as before.
const LIMIT = 600;

/** One part: its label, its text with the claims in it underlined, and how it was read.
 * `clamp` keeps it to three lines, for the panel folded away. */
function Part({ part, spans, thumb, clamp }: { part: ReadPart; spans: Span[]; thumb: string | null; clamp: boolean }) {
  const [all, setAll] = useState(false);
  const text = part.text.trim() ? part.text : "";
  const long = !clamp && text.length > LIMIT;
  const upTo = long && !all ? LIMIT : text.length;
  const time = part.kind === "transcript" ? heard(part) : null;
  return (
    <div className="flex gap-3">
      {thumb && <Thumb src={thumb} alt={labelOf(part)} />}
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs font-semibold text-ink3">
          <span>{labelOf(part)}</span>
          {!part.checked && <span className="rounded-md bg-sf2 px-1.5 py-px font-medium">Description only, not checked</span>}
          {part.complete === false && <span className="rounded-md bg-mis-soft px-1.5 py-px font-medium text-mis">Read in part</span>}
          {time && <span className="font-medium">· {time}</span>}
        </div>
        {text ? (
          <p
            className={`mt-1 whitespace-pre-line ${clamp ? "line-clamp-3" : ""} ${part.checked ? "text-[15px] leading-relaxed text-ink" : "text-sm leading-relaxed text-ink3"}`}
          >
            {marked(text, spans, upTo)}
            {upTo < text.length ? "…" : ""}
          </p>
        ) : (
          <p className="mt-1 text-sm text-ink3">
            {part.kind === "picture_text" ? "No text in this picture, so the picture itself was checked." : "Nothing was read here."}
          </p>
        )}
        {long && (
          <button type="button" onClick={() => setAll(!all)} className="mt-1.5 text-sm font-semibold text-acc-ink">
            {all ? "Show less" : "Show all the text"}
          </button>
        )}
        {part.note?.trim() && <p className="mt-1 text-xs text-ink3">{part.note}</p>}
      </div>
    </div>
  );
}

/** Who posted it, where and when; for a link, the site; for an upload, what it was. */
function Header({ read }: { read: InputRead }) {
  const when = day(read.published_at);
  if (read.kind === "social_post") {
    const handle = read.handle?.replace(/^@/, "");
    return (
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-sm">
        <span className="rounded-md bg-sf2 px-2 py-0.5 text-xs font-semibold text-ink2">{platformName(read.platform) ?? "Post"}</span>
        {read.author?.trim() && <span className="font-semibold text-ink">{read.author}</span>}
        {handle && <span className="text-ink3">@{handle}</span>}
        {when && <span className="text-ink3">· {when}</span>}
        {read.url && (
          <a href={read.url} target="_blank" rel="noopener noreferrer" className="ml-auto text-xs font-semibold text-acc-ink">
            Open the {readNoun(read)} →
          </a>
        )}
      </div>
    );
  }
  if (read.kind === "link") {
    return (
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-sm">
        <span className="rounded-md bg-sf2 px-2 py-0.5 text-xs font-semibold text-ink2">Page</span>
        {read.url && <span className="min-w-0 truncate font-semibold text-ink">{host(read.url)}</span>}
        {when && <span className="text-ink3">· {when}</span>}
        {read.url && (
          <a href={read.url} target="_blank" rel="noopener noreferrer" className="ml-auto text-xs font-semibold text-acc-ink">
            Open the page →
          </a>
        )}
      </div>
    );
  }
  const what = { text: "Your message", image: "Your picture", pdf: "Your PDF", video: "Your video" }[read.kind as string];
  return what ? <div className="text-sm font-semibold text-ink">{what}</div> : null;
}

// What kind of picture an uploaded one is, as the picture reader says (image_reading.kind).
export const IMAGE_KIND: Record<string, string> = {
  NEWS_ARTICLE: "News article",
  SOCIAL_POST: "Social media post",
  CHAT_MESSAGE: "Chat forward",
  TV_GRAPHIC: "TV news graphic",
  POSTER: "Poster",
  DOCUMENT: "Document",
  PHOTO: "Photo",
  MEME: "Meme",
};

export function WhatWeRead({
  read,
  claims,
  nothing,
  preview,
  picture,
}: {
  read: InputRead;
  claims: Claim[];
  // Nothing in it to fact-check: no claim to underline.
  nothing: boolean;
  // The person's own upload, shown beside what was read from it.
  preview?: string | null;
  // What kind of picture an uploaded one is, and whose name it shows.
  picture?: { kind?: string | null; publisher?: string | null } | null;
}) {
  // A field left out is read as the contract's default, so one part sent short of a
  // field never takes the panel down.
  const parts = (read.parts ?? []).map((p) => ({ ...p, text: typeof p.text === "string" ? p.text : "", checked: p.checked ?? !DESCRIBED.has(p.kind) }));
  const gaps = read.gaps ?? [];
  const limits = read.limits ?? [];
  const missed = read.complete === false || gaps.length > 0;
  const withheld = !!read.verdict_withheld;
  // Open when something was missed or nothing was decided: what was read is then the
  // point. Otherwise the verdict is, and this stays to three lines until asked.
  const [open, setOpen] = useState(missed || withheld);
  const spans = nothing ? parts.map(() => []) : spansByPart(parts, claims);
  const shown = parts.map((p, i) => ({ p, i })).filter(({ p }) => p.text.trim() || p.kind === "picture_text");
  const first = shown.find(({ p }) => p.checked) ?? shown[0];
  const longFirst = !!first && (first.p.text.length > 240 || first.p.text.split("\n").length > 3);
  const collapsible = shown.length > 1 || longFirst;
  const folded = collapsible && !open;
  const blocking = gaps.some((g) => g.blocking);
  const noun = readNoun(read);

  // A picture shows once, beside the first part read from it.
  const seen = new Set<string>();
  const thumbOf = (p: ReadPart): string | null => {
    const src = p.media_url ? served(p.media_url) : read.kind === "image" && preview ? preview : null;
    if (!src || seen.has(src)) return null;
    seen.add(src);
    return src;
  };
  const visible = folded ? (first ? [first] : []) : shown;
  const thumbs = visible.map(({ p }) => thumbOf(p));
  const marks = [...new Set(visible.flatMap(({ i }) => spans[i].map((s) => s.mark)))];

  return (
    <div className="rounded-[14px] border border-line bg-sf p-4 shadow-card sm:p-5">
      <div className="text-xs font-semibold text-ink3">What Factify read</div>
      <div className="mt-2">
        <Header read={read} />
      </div>

      {read.kind === "image" && (picture?.kind || picture?.publisher?.trim()) && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {picture.kind && <span className="rounded-full bg-sf2 px-2.5 py-0.5 text-xs font-medium text-ink2">{IMAGE_KIND[picture.kind] ?? "Picture"}</span>}
          {picture.publisher?.trim() && <span className="rounded-full bg-sf2 px-2.5 py-0.5 text-xs font-medium text-ink2">Shows: {picture.publisher.trim()}</span>}
        </div>
      )}

      {missed && (
        <div className={`mt-3 rounded-[10px] px-3.5 py-3 ${blocking ? "bg-mis-soft" : "bg-sf2"}`} role="status">
          <p className="text-sm font-semibold text-ink">Factify could only read part of this {noun}.</p>
          {gaps.length > 0 && (
            <ul className="mt-1.5 space-y-1 text-sm leading-snug text-ink2">
              {gaps.map((g, i) => (
                <li key={`${g.code}-${i}`} className="flex gap-2">
                  <span aria-hidden="true" className="mt-[0.55em] h-1 w-1 shrink-0 rounded-full bg-ink3" />
                  <span>{gapLine(g, parts)}</span>
                </li>
              ))}
            </ul>
          )}
          {read.checked_partially && (
            <p className="mt-2 text-sm text-ink2">You asked Factify to check what it could read, so this answer is about that part only.</p>
          )}
        </div>
      )}

      {visible.length > 0 ? (
        <div className="mt-3.5 space-y-4">
          {visible.map(({ p, i }, n) => (
            <Part key={i} part={p} spans={spans[i]} thumb={thumbs[n]} clamp={folded} />
          ))}
        </div>
      ) : (
        <p className="mt-3 text-sm text-ink3">Nothing could be read from it.</p>
      )}

      {collapsible && (
        <button type="button" onClick={() => setOpen(!open)} className="mt-2.5 text-sm font-semibold text-acc-ink" aria-expanded={open}>
          {open ? "Show less" : shown.length > 1 ? `Show all ${shown.length} parts` : "Show all"}
        </button>
      )}

      <MarkKey marks={marks} />

      {/* Not about reading, and shown folded or not: which checks could not run. */}
      {limits.length > 0 && (
        <div className="mt-3 space-y-1 border-t border-line pt-3">
          {limits.map((l) => (
            <p key={l} className="text-xs leading-relaxed text-ink3">
              {l}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
