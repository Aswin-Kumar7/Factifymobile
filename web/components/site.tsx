"use client";

import Link from "next/link";
import { useState } from "react";
import { Wordmark } from "./ui";

const links = [
  { href: "/#how", label: "How it works" },
  { href: "/#teams", label: "For teams" },
  { href: "/#pricing", label: "Pricing" },
  { href: "/docs", label: "API docs" },
];

export function SiteHeader() {
  const [open, setOpen] = useState(false);
  return (
    <header className="sticky top-0 z-30 border-b border-line/70 bg-bg/90 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6">
        <Wordmark size={34} />
        <nav className="hidden items-center gap-7 text-[15px] text-ink2 md:flex">
          {links.map((l) => (
            <Link key={l.href} href={l.href} className="hover:text-ink">
              {l.label}
            </Link>
          ))}
        </nav>
        <div className="hidden items-center gap-2 md:flex">
          <Link href="/signin" className="rounded-xl px-4 py-2 text-[15px] font-semibold text-ink hover:bg-sf2">
            Sign in
          </Link>
          <Link href="/signup" className="rounded-xl bg-acc px-4 py-2 text-[15px] font-semibold text-on-acc hover:brightness-110">
            Start free
          </Link>
        </div>
        <button
          className="rounded-lg p-2 text-ink md:hidden"
          aria-label={open ? "Close menu" : "Open menu"}
          aria-expanded={open}
          onClick={() => setOpen(!open)}
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            {open ? <path d="M6 6l12 12M18 6L6 18" /> : <path d="M4 7h16M4 12h16M4 17h16" />}
          </svg>
        </button>
      </div>
      {open && (
        <nav className="border-t border-line bg-bg px-4 pb-4 md:hidden">
          {links.map((l) => (
            <Link key={l.href} href={l.href} onClick={() => setOpen(false)} className="block py-3 text-base text-ink">
              {l.label}
            </Link>
          ))}
          <div className="mt-2 grid grid-cols-2 gap-2">
            <Link href="/signin" className="rounded-xl border border-line bg-sf py-2.5 text-center font-semibold text-ink">
              Sign in
            </Link>
            <Link href="/signup" className="rounded-xl bg-acc py-2.5 text-center font-semibold text-on-acc">
              Start free
            </Link>
          </div>
        </nav>
      )}
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer className="border-t border-line">
      <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-10 sm:flex-row sm:items-start sm:justify-between sm:px-6">
        <div className="max-w-xs">
          <Wordmark size={28} />
          <p className="mt-3 text-sm text-ink2">Check before you share. Every answer comes with its sources.</p>
        </div>
        <div className="grid grid-cols-2 gap-x-12 gap-y-2 text-sm text-ink2">
          <Link href="/docs" className="hover:text-ink">API docs</Link>
          <Link href="/privacy" className="hover:text-ink">Privacy</Link>
          <Link href="/#pricing" className="hover:text-ink">Pricing</Link>
          <Link href="/terms" className="hover:text-ink">Terms</Link>
          <Link href="/signin" className="hover:text-ink">Sign in</Link>
          <a href="mailto:aswin.aswin5640@gmail.com" className="hover:text-ink">Contact</a>
        </div>
      </div>
      <div className="mx-auto max-w-6xl px-4 pb-8 text-xs text-ink3 sm:px-6">© {new Date().getFullYear()} Factify</div>
    </footer>
  );
}

export function Prose({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto max-w-3xl px-4 py-12 sm:px-6 sm:py-16 [&_a]:text-acc-ink [&_a]:underline [&_code]:rounded [&_code]:bg-sf2 [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:text-[0.9em] [&_h1]:font-serif [&_h1]:text-4xl [&_h1]:font-medium [&_h1]:tracking-tight [&_h1]:sm:text-5xl [&_h2]:mt-10 [&_h2]:mb-3 [&_h2]:font-serif [&_h2]:text-2xl [&_h2]:font-medium [&_h3]:mt-6 [&_h3]:mb-2 [&_h3]:font-semibold [&_li]:ml-5 [&_li]:list-disc [&_li]:py-0.5 [&_p]:my-3 [&_p]:leading-relaxed [&_p]:text-ink2 [&_li]:text-ink2 [&_table]:w-full [&_td]:border-b [&_td]:border-line [&_td]:py-2 [&_td]:pr-3 [&_th]:border-b [&_th]:border-line [&_th]:py-2 [&_th]:pr-3 [&_th]:text-left">
      {children}
    </div>
  );
}
