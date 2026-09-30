"use client";

// Personal history, kept in this browser only (as the phone keeps it on the phone):
// the server never links what someone checked to their account.

export type HistoryItem = {
  case_id: string;
  title: string;
  verdict: string;
  kind: "text" | "link" | "file";
  at: string;
  account: string;
};

const KEY = "fct_history";

export function readHistory(): HistoryItem[] {
  try {
    return JSON.parse(localStorage.getItem(KEY) || "[]");
  } catch {
    return [];
  }
}

export function addHistory(item: HistoryItem) {
  try {
    const list = [item, ...readHistory().filter((h) => h.case_id !== item.case_id)].slice(0, 200);
    localStorage.setItem(KEY, JSON.stringify(list));
  } catch {}
}

export function clearHistory() {
  try {
    localStorage.removeItem(KEY);
  } catch {}
}
