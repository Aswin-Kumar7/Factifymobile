"use client";

// Where the Android app is downloaded from, and what is said about the file. The
// app is not on the Play Store yet: the signed release APK is served from our own
// server at /downloads, beside factify.json, which scripts/publish_apk.py writes
// with the version, size, SHA-256 and oldest Android it runs on. The page reads it
// when it opens, so publishing a new APK needs no rebuild of the website.

import { useEffect, useState } from "react";

export const APK_URL = process.env.NEXT_PUBLIC_APK_URL || "/downloads/factify.apk";
const FACTS_URL = process.env.NEXT_PUBLIC_APK_FACTS_URL || "/downloads/factify.json";

type ApkFacts = { version?: string; size?: string; sha256?: string; min_android?: string };

let cached: Promise<ApkFacts | null> | null = null;

/** What is known about the published APK; null until read, or when nothing is published. */
export function useApkFacts(): ApkFacts | null {
  const [facts, setFacts] = useState<ApkFacts | null>(null);
  useEffect(() => {
    cached ??= fetch(FACTS_URL, { cache: "no-store" })
      .then((r) => (r.ok ? (r.json() as Promise<ApkFacts>) : null))
      .catch(() => null);
    let live = true;
    cached.then((f) => live && setFacts(f));
    return () => {
      live = false;
    };
  }, []);
  return facts;
}

/** "Version 1.0.0 · 59 MB · Android 7 or newer", with only what is known. */
export function describeApk(facts: ApkFacts | null) {
  if (!facts) return "For Android phones";
  return [facts.version && `Version ${facts.version}`, facts.size, facts.min_android ? `Android ${facts.min_android} or newer` : "For Android phones"]
    .filter(Boolean)
    .join(" · ");
}

export function ApkFactsLine({ className = "" }: { className?: string }) {
  const facts = useApkFacts();
  return <span className={className}>{describeApk(facts)}</span>;
}
