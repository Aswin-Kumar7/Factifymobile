"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { authAction } from "@/lib/api";
import { n, roleName } from "@/lib/format";
import { useAccount } from "./account";
import { Seal, Spinner } from "./ui";

type Item = { href: string; label: string; icon: keyof typeof icons; exact?: boolean };

const icons = {
  check: "M9 12l2 2 4-4M21 12a9 9 0 11-18 0 9 9 0 0118 0z",
  history: "M12 8v4l3 3M3.05 11a9 9 0 111.1 4.5M3 4v5h5",
  credits: "M12 6v12M8.5 9.5C8.5 8 10 7 12 7s3.5 1 3.5 2.5S14 12 12 12s-3.5 1-3.5 2.5S10 17 12 17s3.5-1 3.5-2.5",
  profile: "M16 7a4 4 0 11-8 0 4 4 0 018 0zM4 21a8 8 0 0116 0",
  overview: "M4 13h6V4H4v9zm0 7h6v-4H4v4zm10 0h6v-9h-6v9zm0-16v4h6V4h-6z",
  members: "M17 20v-2a4 4 0 00-4-4H7a4 4 0 00-4 4v2M10 10a4 4 0 100-8 4 4 0 000 8zM21 20v-2a4 4 0 00-3-3.9M16 2.1a4 4 0 010 7.8",
  keys: "M15 7a4 4 0 11-3.9 4.9L3 20v-3h3v-3h3l2.1-2.1A4 4 0 0115 7z",
  usage: "M3 3v18h18M7 15l4-4 3 3 5-6",
  billing: "M3 7h18v12H3zM3 11h18M7 15h4",
  settings: "M12 15a3 3 0 100-6 3 3 0 000 6zM19.4 15a1.7 1.7 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.8-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1.1-1.5 1.7 1.7 0 00-1.8.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.8 1.7 1.7 0 00-1.5-1H3a2 2 0 110-4h.1a1.7 1.7 0 001.5-1.1 1.7 1.7 0 00-.3-1.8l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.8.3H9a1.7 1.7 0 001-1.5V3a2 2 0 114 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.8-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.8V9a1.7 1.7 0 001.5 1H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z",
  audit: "M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 012-2h2a2 2 0 012 2M9 5h6M9 12h6M9 16h4",
  admin: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6l8-3z",
  plus: "M12 5v14M5 12h14",
};

function Icon({ name }: { name: keyof typeof icons }) {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={icons[name]} />
    </svg>
  );
}

function Switcher({ onPick }: { onPick: () => void }) {
  const { me, orgs, account, current, choose } = useAccount();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const close = (e: MouseEvent) => box.current && !box.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const label = current ? current.name : "Personal";
  const sub = current ? `${roleName[current.role]} · ${n(current.balance)} credits` : `${n(me?.credits.balance)} credits`;
  return (
    <div ref={box} className="relative">
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-haspopup="listbox"
        className="flex w-full items-center gap-3 rounded-xl border border-line bg-sf px-3 py-2.5 text-left hover:bg-sf2"
      >
        <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg font-semibold ${current ? "bg-acc text-on-acc" : "bg-acc-soft text-acc-ink"}`}>
          {label.slice(0, 1).toUpperCase()}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-semibold text-ink">{label}</span>
          <span className="block truncate text-xs text-ink3">{sub}</span>
        </span>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-ink3">
          <path d="M8 9l4-4 4 4M16 15l-4 4-4-4" />
        </svg>
      </button>
      {open && (
        <div role="listbox" className="absolute top-full right-0 left-0 z-40 mt-1.5 rounded-xl border border-line bg-sf p-1.5 shadow-xl">
          <div className="px-2.5 pt-1.5 pb-1 text-xs font-semibold text-ink3">Check and pay as</div>
          {[{ id: "personal", name: "Personal", note: `${n(me?.credits.balance)} free credits` }, ...orgs.map((o) => ({ id: o.id, name: o.name, note: `${roleName[o.role]} · ${n(o.balance)} credits` }))].map((o) => (
            <button
              key={o.id}
              role="option"
              aria-selected={account === o.id}
              onClick={() => {
                choose(o.id);
                setOpen(false);
                onPick();
                router.push(o.id === "personal" ? "/app/check" : `/app/org/${o.id}`);
              }}
              className={`flex w-full items-center justify-between gap-2 rounded-lg px-2.5 py-2 text-left text-sm hover:bg-sf2 ${account === o.id ? "bg-sf2" : ""}`}
            >
              <span className="min-w-0">
                <span className="block truncate font-semibold text-ink">{o.name}</span>
                <span className="block truncate text-xs text-ink3">{o.note}</span>
              </span>
              {account === o.id && <span className="text-acc-ink">✓</span>}
            </button>
          ))}
          <Link
            href="/app/org/new"
            onClick={() => {
              setOpen(false);
              onPick();
            }}
            className="mt-1 flex items-center gap-2 rounded-lg border-t border-line px-2.5 py-2.5 text-sm font-semibold text-acc-ink hover:bg-sf2"
          >
            <Icon name="plus" /> Create an organisation
          </Link>
        </div>
      )}
    </div>
  );
}

function NavLink({ item, onClick }: { item: Item; onClick: () => void }) {
  const path = usePathname();
  const active = path === item.href || (!item.exact && path.startsWith(item.href + "/"));
  return (
    <Link
      href={item.href}
      onClick={onClick}
      aria-current={active ? "page" : undefined}
      className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-[15px] font-medium ${active ? "bg-acc-soft text-acc-ink" : "text-ink2 hover:bg-sf2 hover:text-ink"}`}
    >
      <Icon name={item.icon} />
      {item.label}
    </Link>
  );
}

function Nav({ onNavigate }: { onNavigate: () => void }) {
  const { me, current } = useAccount();
  const base: Item[] = [
    { href: "/app/check", label: "Check", icon: "check", exact: true },
    { href: "/app/history", label: "History", icon: "history" },
  ];
  const personal: Item[] = [
    { href: "/app/credits", label: "Credits", icon: "credits" },
    { href: "/app/profile", label: "Profile", icon: "profile" },
  ];
  const org: Item[] = [];
  if (current) {
    const o = `/app/org/${current.id}`;
    org.push({ href: o, label: "Overview", icon: "overview", exact: true });
    org.push({ href: `${o}/members`, label: "Members", icon: "members" });
    if (current.role !== "member") org.push({ href: `${o}/keys`, label: "API keys", icon: "keys" });
    org.push({ href: `${o}/usage`, label: "Usage", icon: "usage" });
    if (current.role === "owner") {
      org.push({ href: `${o}/billing`, label: "Billing", icon: "billing" });
      org.push({ href: `${o}/settings`, label: "Settings", icon: "settings" });
      org.push({ href: `${o}/audit`, label: "Audit log", icon: "audit" });
    }
  }
  return (
    <nav className="flex flex-col gap-0.5">
      {base.map((i) => <NavLink key={i.href} item={i} onClick={onNavigate} />)}
      {current && (
        <>
          <div className="mt-5 mb-1 truncate px-3 text-xs font-semibold tracking-wide text-ink3 uppercase">{current.name}</div>
          {org.map((i) => <NavLink key={i.href} item={i} onClick={onNavigate} />)}
        </>
      )}
      <div className="mt-5 mb-1 px-3 text-xs font-semibold tracking-wide text-ink3 uppercase">You</div>
      {personal.map((i) => <NavLink key={i.href} item={i} onClick={onNavigate} />)}
      {me?.is_staff && (
        <>
          <div className="mt-5 mb-1 px-3 text-xs font-semibold tracking-wide text-ink3 uppercase">Factify</div>
          <NavLink item={{ href: "/app/admin", label: "Admin", icon: "admin" }} onClick={onNavigate} />
        </>
      )}
    </nav>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  const { me, loading } = useAccount();
  const [open, setOpen] = useState(false);
  const path = usePathname();
  useEffect(() => setOpen(false), [path]);

  async function signOut() {
    await authAction("logout").catch(() => undefined);
    try {
      localStorage.removeItem("fct_account");
    } catch {}
    window.location.href = "/";
  }

  const sidebar = (
    <div className="flex h-full flex-col gap-5 p-4">
      <Link href="/" className="flex items-center gap-2.5 px-1 font-serif text-2xl font-semibold tracking-tight text-ink">
        <Seal size={32} /> Factify
      </Link>
      <Switcher onPick={() => setOpen(false)} />
      <div className="min-h-0 flex-1 overflow-y-auto">
        <Nav onNavigate={() => setOpen(false)} />
      </div>
      <div className="border-t border-line pt-3">
        <div className="truncate px-1 text-sm font-semibold text-ink">{me?.name || me?.email?.split("@")[0]}</div>
        <div className="truncate px-1 text-xs text-ink3">{me?.email}</div>
        <button onClick={signOut} className="mt-2 w-full rounded-xl px-3 py-2 text-left text-sm font-semibold text-ink2 hover:bg-sf2 hover:text-ink">
          Sign out
        </button>
      </div>
    </div>
  );

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[272px_1fr]">
      <aside className="sticky top-0 hidden h-dvh border-r border-line bg-bg lg:block">{sidebar}</aside>

      <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-line bg-bg/95 px-4 backdrop-blur lg:hidden">
        <Link href="/app/check" className="flex items-center gap-2 font-serif text-xl font-semibold text-ink">
          <Seal size={28} /> Factify
        </Link>
        <button onClick={() => setOpen(true)} aria-label="Open menu" className="-mr-2 rounded-lg p-2 text-ink">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M4 7h16M4 12h16M4 17h16" />
          </svg>
        </button>
      </header>
      {open && (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Menu">
          <div className="absolute inset-0 bg-black/40" onClick={() => setOpen(false)} />
          <div className="absolute inset-y-0 left-0 w-[86%] max-w-[320px] bg-bg shadow-2xl">{sidebar}</div>
        </div>
      )}

      <main className="min-w-0 px-4 py-6 sm:px-6 lg:px-10 lg:py-10">
        <div className="mx-auto max-w-5xl">
          {loading ? (
            <div className="flex items-center gap-2 py-20 text-ink2">
              <Spinner /> Loading…
            </div>
          ) : (
            children
          )}
        </div>
      </main>
    </div>
  );
}
