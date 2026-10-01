"use client";

// Personal history, kept in this browser only (as the phone keeps it on the phone):
// the server never links what someone checked to their account. Kept per person, so
// two people signing in on one browser never see each other's checks.
//
// A check is written here as soon as the server accepts it, as PENDING, so leaving
// the page while it runs leaves it in History; its verdict is filled in when it is
// answered, here or when History next opens. FAILED: it ended without an answer.

export const PENDING = "PENDING";
export const FAILED = "FAILED";

export type HistoryItem = {
  case_id: string;
  title: string;
  verdict: string;
  kind: "text" | "link" | "file" | "image" | "pdf" | "video";
  at: string;
  account: string;
};

// Before history was kept per person: no owner is known, so it is not shown.
const SHARED_KEY = "fct_history";
let KEY = "";

/** Whose history is read and written from now on; set when the account loads. */
export function setHistoryOwner(userId: string) {
  KEY = `fct_history:${userId}`;
  try {
    localStorage.removeItem(SHARED_KEY);
  } catch {}
}

export function readHistory(): HistoryItem[] {
  if (!KEY) return [];
  try {
    return JSON.parse(localStorage.getItem(KEY) || "[]");
  } catch {
    return [];
  }
}

export function addHistory(item: HistoryItem) {
  if (!KEY) return;
  try {
    const list = [item, ...readHistory().filter((h) => h.case_id !== item.case_id)].slice(0, 200);
    localStorage.setItem(KEY, JSON.stringify(list));
  } catch {}
}

/** Fill in what is now known about a check, under its id when it was accepted. A
 * repeat served from the cache answers under the case it was first recorded as, so
 * `changes.case_id` can move the entry to that id. */
export function updateHistory(caseId: string, changes: Partial<HistoryItem>): HistoryItem[] {
  if (!KEY) return [];
  try {
    const list = readHistory();
    const at = list.findIndex((h) => h.case_id === caseId);
    if (at < 0) return list;
    const next = { ...list[at], ...changes };
    const rest = list.filter((h, i) => i !== at && h.case_id !== next.case_id);
    rest.splice(Math.min(at, rest.length), 0, next);
    localStorage.setItem(KEY, JSON.stringify(rest));
    return rest;
  } catch {
    return readHistory();
  }
}

export function removeHistory(caseId: string) {
  if (!KEY) return;
  try {
    localStorage.setItem(KEY, JSON.stringify(readHistory().filter((h) => h.case_id !== caseId)));
  } catch {}
}

export function clearHistory() {
  if (!KEY) return;
  try {
    localStorage.removeItem(KEY);
  } catch {}
}
