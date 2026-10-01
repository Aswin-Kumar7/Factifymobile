"use client";

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

export function SiteHeader() {
  const [open, setOpen] = useState(false);
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-bg/80 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-[1200px] items-center justify-between gap-4 px-4 sm:px-8">
        <div className="flex items-center gap-7">
          <Wordmark />
          <nav className="hidden items-center gap-0.5 md:flex" aria-label="Main">
            {links.map((l) => (
              <Link key={l.href} href={l.href} className="rounded-lg px-2.5 py-1.5 text-sm text-ink2 transition-colors hover:bg-hover hover:text-ink">
                {l.label}
              </Link>
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-1.5">
          <ThemeButton />
          <Link href="/signin" className="hidden rounded-lg px-2.5 py-1.5 text-sm text-ink2 hover:bg-hover hover:text-ink md:inline-block">
            Sign in
          </Link>
          <Link href="/download" className="hidden h-8.5 items-center rounded-lg border border-line2 px-3 text-[13.5px] font-medium text-ink hover:bg-hover md:inline-flex">
            Get the app
          </Link>
          <Link href="/signup" className="inline-flex h-8.5 items-center rounded-lg bg-acc px-3 text-[13.5px] font-medium text-on-acc hover:bg-acc-h">
            Try it free
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
        <nav className="border-t border-line bg-bg px-4 pb-4 md:hidden" aria-label="Main">
          {links.map((l) => (
            <Link key={l.href} href={l.href} onClick={() => setOpen(false)} className="block py-3 text-base text-ink">
              {l.label}
            </Link>
          ))}
          <div className="mt-2 grid grid-cols-2 gap-2">
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
      ["Contact us", "mailto:aswin.aswin5640@gmail.com"],
    ],
  },
];

export function SiteFooter() {
  return (
    <footer className="border-t border-line">
      <div className="mx-auto max-w-[1200px] px-4 pt-14 pb-9 sm:px-8">
        <div className="grid grid-cols-2 gap-8 md:grid-cols-[minmax(0,1.6fr)_repeat(4,minmax(0,1fr))]">
          <div className="col-span-2 flex flex-col gap-3 md:col-span-1">
            <Wordmark size={20} />
            <p className="max-w-[250px] text-sm leading-relaxed text-ink3">Fact-checking for the forwards in your chats.</p>
          </div>
          {footer.map((col) => (
            <div key={col.title} className="flex flex-col gap-2.5">
              <span className="mb-1 text-sm text-ink">{col.title}</span>
              {col.links.map(([label, href]) =>
                href.startsWith("mailto:") ? (
                  <a key={label} href={href} className="text-sm text-ink3 transition-colors hover:text-ink">
                    {label}
                  </a>
                ) : (
                  <Link key={label} href={href} className="text-sm text-ink3 transition-colors hover:text-ink">
                    {label}
                  </Link>
                ),
              )}
            </div>
          ))}
        </div>
        <div className="mt-14 border-t border-line pt-5 text-[13px] text-ink3">© {new Date().getFullYear()} Factify</div>
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
