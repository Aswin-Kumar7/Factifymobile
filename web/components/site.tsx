"use client";

import Image from "next/image";
import Link from "next/link";
import { useState } from "react";
import { ThemeButton } from "./theme";
import { Wordmark } from "./ui";

const links = [
  { href: "/#how", label: "How it works" },
  { href: "/#features", label: "Features" },
  { href: "/#pricing", label: "Pricing" },
  { href: "/#teams", label: "Teams & API" },
  { href: "/#faq", label: "FAQ" },
];

/** `wide` lines the bar up with pages that use the full width, like the API docs. */
export function SiteHeader({ wide = false }: { wide?: boolean }) {
  const width = wide ? "max-w-[1480px]" : "max-w-[1200px]";
  const [open, setOpen] = useState(false);
  return (
    <header className="sticky top-0 z-30 px-3 pt-3 sm:px-5">
      <div className={`mx-auto flex h-15 ${width} items-center justify-between gap-4 rounded-2xl border border-line bg-bg/70 px-4 shadow-card backdrop-blur-xl sm:px-5`}>
        <div className="flex items-center gap-3">
          <Wordmark />
          <span className="hidden h-5 w-px bg-line2 lg:block" />
          <span className="hidden items-center gap-2 text-[12px] text-ink3 lg:flex" title="Built for the ZeAI #MadeInIndia Hackathon 2026">
            <span>for</span>
            <ZeaiLogo height={20} />
          </span>
        </div>
        <nav className="hidden items-center gap-1 rounded-xl border border-line bg-sf/50 p-1 md:flex" aria-label="Main">
          {links.map((l) => (
            <Link key={l.href} href={l.href} className="rounded-lg px-3 py-1.5 text-[13.5px] text-ink2 transition-colors hover:bg-hover hover:text-ink">
              {l.label}
            </Link>
          ))}
        </nav>
        <div className="flex items-center gap-1.5">
          <ThemeButton />
          <Link href="/signin" className="hidden rounded-lg px-3 py-1.5 text-[13.5px] text-ink2 transition-colors hover:bg-hover hover:text-ink md:inline-block">
            Sign in
          </Link>
          <Link
            href="/signup"
            className="group inline-flex h-9 items-center gap-1.5 rounded-[10px] bg-acc px-3.5 text-[13.5px] font-medium text-on-acc shadow-[0_6px_20px_-8px_var(--glow)] transition-colors hover:bg-acc-h"
          >
            Try it free
            <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="transition-transform group-hover:translate-x-0.5" aria-hidden="true">
              <path d="M3 8h10M9 4l4 4-4 4" />
            </svg>
          </Link>
          <button
            className="rounded-lg p-2 text-ink md:hidden"
            aria-label={open ? "Close menu" : "Open menu"}
            aria-expanded={open}
            onClick={() => setOpen(!open)}
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
              {open ? <path d="M6 6l12 12M18 6L6 18" /> : <path d="M4 7h16M4 12h16M4 17h16" />}
            </svg>
          </button>
        </div>
      </div>
      {open && (
        <nav className={`mx-auto mt-2 ${width} rounded-2xl border border-line bg-bg/95 px-4 pb-4 shadow-card backdrop-blur-xl md:hidden`} aria-label="Main">
          {links.map((l) => (
            <Link key={l.href} href={l.href} onClick={() => setOpen(false)} className="block border-b border-line py-3 text-base text-ink last:border-b-0">
              {l.label}
            </Link>
          ))}
          <div className="mt-3 grid grid-cols-2 gap-2">
            <Link href="/signin" className="rounded-[10px] border border-line2 py-2.5 text-center font-medium text-ink">
              Sign in
            </Link>
            <Link href="/download" className="rounded-[10px] border border-line2 py-2.5 text-center font-medium text-ink">
              Get the app
            </Link>
          </div>
        </nav>
      )}
    </header>
  );
}

// Only pages that exist.
const footer = [
  {
    title: "Product",
    links: [
      ["How it works", "/#how"],
      ["Features", "/#features"],
      ["Pricing", "/#pricing"],
      ["Android app", "/download"],
    ],
  },
  {
    title: "Developers",
    links: [
      ["API docs", "/docs"],
      ["Teams & organisations", "/#teams"],
    ],
  },
  {
    title: "Legal",
    links: [
      ["Privacy policy", "/privacy"],
      ["Terms of use", "/terms"],
    ],
  },
  {
    title: "Account",
    links: [
      ["Sign in", "/signin"],
      ["Create an account", "/signup"],
    ],
  },
];

/** The ZeAI logo for the theme on screen: the original on light pages, white lettering
 * on dark ones (its "AI" is black). `onDark` forces the white one, for dark panels. */
export function ZeaiLogo({ height = 24, onDark = false, className = "" }: { height?: number; onDark?: boolean; className?: string }) {
  const width = Math.round(height * 2.68);
  return (
    <span className={`inline-flex shrink-0 ${className}`} style={{ height }}>
      <Image src="/zeai-dark.png" alt="ZeAI" width={width} height={height} className={`h-full w-auto ${onDark ? "" : "[[data-theme=light]_&]:hidden"}`} />
      {!onDark && <Image src="/zeai-light.png" alt="" aria-hidden="true" width={width} height={height} className="hidden h-full w-auto [[data-theme=light]_&]:block" />}
    </span>
  );
}

/** "Built for the ZeAI #MadeInIndia Hackathon", with the organiser's logo. */
export function ZeaiMark({ dark = false }: { dark?: boolean }) {
  return (
    <span
      className={`inline-flex items-center gap-3 self-start rounded-full border py-1.5 pr-4 pl-3.5 text-[13px] backdrop-blur ${
        dark ? "border-white/15 bg-white/[.06] text-[#cfe3d8]" : "border-line2 bg-sf/60 text-ink2"
      }`}
    >
      <ZeaiLogo height={26} onDark={dark} />
      <span className={`h-4 w-px ${dark ? "bg-white/20" : "bg-line2"}`} />
      Built for the ZeAI #MadeInIndia Hackathon 2026
    </span>
  );
}

export function SiteFooter() {
  return (
    <footer className="relative border-t border-line bg-sf2/40">
      <div aria-hidden="true" className="absolute inset-x-0 -top-px h-px bg-linear-to-r from-transparent via-acc-ink/50 to-transparent" />
      <div className="mx-auto max-w-[1200px] px-4 pt-16 pb-9 sm:px-8">
        <div className="grid grid-cols-2 gap-8 md:grid-cols-[minmax(0,1.8fr)_repeat(4,minmax(0,1fr))]">
          <div className="col-span-2 flex flex-col gap-4 md:col-span-1">
            <Wordmark size={20} />
            <p className="max-w-[270px] text-sm leading-relaxed text-ink3">Fact-checking for the forwards in your chats &mdash; with the source that proves it.</p>
            <div className="mt-2 flex max-w-[360px] items-center gap-3.5 rounded-2xl border border-line bg-sf p-3.5 shadow-card">
              <ZeaiLogo height={30} />
              <span className="text-[12.5px] leading-snug text-ink3">
                Built for the <span className="text-ink">ZeAI #MadeInIndia Hackathon 2026</span> &middot; ZAIML-005 &middot; Team Cipher
              </span>
            </div>
          </div>
          {footer.map((col) => (
            <div key={col.title} className="flex flex-col gap-2.5">
              <span className="mb-1 text-sm text-ink">{col.title}</span>
              {col.links.map(([label, href]) => (
                <Link key={label} href={href} className="text-sm text-ink3 transition-colors hover:text-ink">
                  {label}
                </Link>
              ))}
            </div>
          ))}
        </div>
        <div className="mt-14 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-5 text-[13px] text-ink3">
          <span>© {new Date().getFullYear()} Factify</span>
          <span>Made in India &middot; Empowering you with the facts</span>
        </div>
      </div>
    </footer>
  );
}

export function Prose({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto max-w-3xl px-4 py-12 sm:px-6 sm:py-16 [&_a]:text-acc-ink [&_a]:underline [&_code]:rounded [&_code]:bg-sf2 [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:text-[0.9em] [&_h1]:text-4xl [&_h1]:font-medium [&_h1]:tracking-tight [&_h1]:sm:text-5xl [&_h2]:mt-10 [&_h2]:mb-3 [&_h2]:text-2xl [&_h2]:font-medium [&_h2]:tracking-tight [&_h3]:mt-6 [&_h3]:mb-2 [&_h3]:font-medium [&_li]:ml-5 [&_li]:list-disc [&_li]:py-0.5 [&_p]:my-3 [&_p]:leading-relaxed [&_p]:text-ink2 [&_li]:text-ink2 [&_table]:w-full [&_td]:border-b [&_td]:border-line [&_td]:py-2 [&_td]:pr-3 [&_th]:border-b [&_th]:border-line [&_th]:py-2 [&_th]:pr-3 [&_th]:text-left">
      {children}
    </div>
  );
}
