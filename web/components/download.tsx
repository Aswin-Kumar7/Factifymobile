"use client";

// Getting the Android app while it is not on the Play Store: the signed APK from our
// own server and the three taps to install it. An iPhone is told the truth - the app
// is Android-only for now - and pointed to the website. On a computer, the page says
// to open it on the phone. The tabs let anyone see either.

import Link from "next/link";
import { useEffect, useState } from "react";
import { APK_URL, describeApk, useApkFacts } from "@/lib/app-download";

type Device = "android" | "iphone" | "computer";

export function DownloadPanel() {
  const [device, setDevice] = useState<Device>("android");
  const [shown, setShown] = useState<"android" | "iphone">("android");
  const facts = useApkFacts();
  useEffect(() => {
    const ua = navigator.userAgent;
    const d: Device = /android/i.test(ua) ? "android" : /iphone|ipad|ipod/i.test(ua) ? "iphone" : "computer";
    setDevice(d);
    setShown(d === "iphone" ? "iphone" : "android");
  }, []);

  const step = (n: number, body: React.ReactNode) => (
    <li className="grid grid-cols-[26px_minmax(0,1fr)] gap-3 text-sm leading-relaxed text-ink2">
      <span className="flex h-6.5 w-6.5 items-center justify-center rounded-full border border-line2 font-mono text-xs text-ink">{n}</span>
      <span>{body}</span>
    </li>
  );

  return (
    <div className="flex flex-col gap-5">
      <div role="tablist" aria-label="Your phone" className="inline-flex self-start rounded-[10px] border border-line p-[3px]">
        {(["android", "iphone"] as const).map((d) => (
          <button
            key={d}
            type="button"
            role="tab"
            aria-selected={shown === d}
            onClick={() => setShown(d)}
            className={`rounded-[7px] px-3.5 py-1.5 text-sm transition-colors ${shown === d ? "bg-hover text-ink" : "text-ink2 hover:text-ink"}`}
          >
            {d === "android" ? "Android" : "iPhone"}
          </button>
        ))}
      </div>

      {shown === "android" ? (
        <div key="android" className="fade-in flex flex-col gap-5">
          <div className="flex items-center gap-3.5">
            <span className="flex h-16 w-16 items-center justify-center rounded-2xl bg-[#0d2a1f]">
              <svg width="34" height="34" viewBox="0 0 32 32" fill="none" aria-hidden="true">
                <path d="M10.8 16.6l3.5 3.5 7.2-7.6" stroke="#5BE4A8" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </span>
            <span>
              <span className="block text-xl font-medium tracking-tight text-ink">Factify for Android</span>
              <span className="block text-[13px] text-ink3">{describeApk(facts)}</span>
            </span>
          </div>
          {device === "computer" && (
            <p className="rounded-[10px] bg-hover px-3.5 py-2.5 text-sm text-ink2">You&apos;re on a computer. Open this page on your Android phone to install the app there.</p>
          )}
          <a href={APK_URL} download className="flex h-13 items-center justify-center gap-2.5 rounded-xl bg-acc text-base font-medium text-on-acc transition-colors hover:bg-acc-h">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M12 4v11M7.5 10.5L12 15l4.5-4.5M5 19h14" />
            </svg>
            Download the app
          </a>
          <div className="rounded-[14px] border border-line bg-sf p-4.5 shadow-card">
            <span className="text-sm font-medium text-ink">Installing takes three taps</span>
            <ol className="mt-3.5 flex flex-col gap-3">
              {step(1, "Open the downloaded file from your notifications.")}
              {step(
                2,
                <>
                  If Android asks, tap <span className="text-ink">Settings → Allow from this source</span>. You only do this once.
                </>,
              )}
              {step(
                3,
                <>
                  Tap <span className="text-ink">Install</span>, then sign in with the same account as the website.
                </>,
              )}
            </ol>
          </div>
          <details className="rounded-[14px] border border-line bg-sf p-4 text-sm text-ink2">
            <summary className="cursor-pointer text-ink">Why isn&apos;t it on the Play Store?</summary>
            <p className="mt-2.5 leading-relaxed">It will be soon. Until then we publish the app here, signed by us{facts?.sha256 ? ". You can check the file you downloaded matches:" : "."}</p>
            {facts?.sha256 && (
              <p className="mt-2 font-mono text-[11px] break-all text-ink3">
                SHA-256 {facts.sha256}
              </p>
            )}
          </details>
        </div>
      ) : (
        <div key="iphone" className="fade-in flex flex-col gap-5">
          <h2 className="text-[1.75rem] leading-tight font-medium tracking-tight text-ink">The app is Android-only for now.</h2>
          <p className="text-base leading-relaxed text-ink2">On iPhone, Factify works in Safari — the same checks, the same account. Add it to your Home Screen and it opens like an app.</p>
          <Link href="/signin" className="flex h-13 items-center justify-center rounded-xl bg-acc text-base font-medium text-on-acc transition-colors hover:bg-acc-h">
            Open Factify in Safari
          </Link>
          <div className="rounded-[14px] border border-line bg-sf p-4.5 shadow-card">
            <span className="text-sm font-medium text-ink">Add it to your Home Screen</span>
            <ol className="mt-3.5 flex flex-col gap-3">
              {step(
                1,
                <>
                  Tap <span className="text-ink">Share</span> at the bottom of Safari.
                </>,
              )}
              {step(
                2,
                <>
                  Choose <span className="text-ink">Add to Home Screen</span>.
                </>,
              )}
              {step(3, "To check a forward, copy it and paste it into Factify.")}
            </ol>
          </div>
        </div>
      )}
    </div>
  );
}
