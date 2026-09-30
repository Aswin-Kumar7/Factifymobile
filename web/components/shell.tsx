"use client";

// The dashboard's frame: an ink-dark sidebar (a drawer on phones), and a top bar with
// the account's credits, the theme switch and the account menu. The admin account
// gets its own sidebar; everyone else never sees an admin link.

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { authAction } from "@/lib/api";
import { n, roleName } from "@/lib/format";
import { useAccount } from "./account";
import { ThemeToggle } from "./theme";
import { Avatar, Seal, Spinner } from "./ui";

type Item = { href: string; label: string; icon: keyof typeof icons; exact?: boolean };

export const icons = {
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
  building: "M4 21V5a1 1 0 011-1h9a1 1 0 011 1v16M15 9h4a1 1 0 011 1v11M8 8h3M8 12h3M8 16h3M3 21h18",
  bolt: "M13 2L4 14h7l-1 8 9-12h-7l1-8z",
};

export function Icon({ name, size = 20 }: { name: keyof typeof icons; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={icons[name]} />
    </svg>
  );
}

function useClickAway(open: boolean, close: () => void) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => box.current && !box.current.contains(e.target as Node) && close();
    const key = (e: KeyboardEvent) => e.key === "Escape" && close();
    document.addEventListener("mousedown", handler);
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("mousedown", handler);
      document.removeEventListener("keydown", key);
    };
  }, [open, close]);
  return box;
}

function Switcher({ onPick }: { onPick: () => void }) {
  const { me, orgs, account, current, choose } = useAccount();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const box = useClickAway(open, () => setOpen(false));

  const label = current ? current.name : "Personal";
  const sub = current ? `${roleName[current.role]} · ${n(current.balance)} credits` : `Free · ${n(me?.credits.balance)} credits`;
  const options = [
    { id: "personal", name: "Personal", note: `Free · ${n(me?.credits.balance)} credits` },
    ...orgs.map((o) => ({ id: o.id, name: o.name, note: `${roleName[o.role]} · ${n(o.balance)} credits` })),
  ];
  return (
    <div ref={box} className="relative">
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-haspopup="listbox"
        className="flex w-full items-center gap-3 rounded-2xl border border-side-line bg-side-2 px-3 py-2.5 text-left transition-colors hover:border-side-ink2/40"
      >
        <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl font-serif text-lg font-semibold ${current ? "bg-mint text-[#0b3d2d]" : "bg-side-line text-side-ink"}`}>
          {label.slice(0, 1).toUpperCase()}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-semibold text-side-ink">{label}</span>
          <span className="tabular block truncate text-xs text-side-ink2">{sub}</span>
        </span>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-side-ink2">
          <path d="M8 9l4-4 4 4M16 15l-4 4-4-4" />
        </svg>
      </button>
      {open && (
        <div role="listbox" className="fade-in absolute top-full right-0 left-0 z-40 mt-2 rounded-2xl border border-line bg-sf p-1.5 shadow-lift">
          <div className="px-2.5 pt-1.5 pb-1 text-[11px] font-semibold tracking-[0.1em] text-ink3 uppercase">Check and pay as</div>
          {options.map((o) => (
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
              className={`flex w-full items-center gap-3 rounded-xl px-2.5 py-2 text-left text-sm hover:bg-sf2 ${account === o.id ? "bg-sf2" : ""}`}
            >
              <Avatar name={o.name} size={30} />
              <span className="min-w-0 flex-1">
                <span className="block truncate font-semibold text-ink">{o.name}</span>
                <span className="tabular block truncate text-xs text-ink3">{o.note}</span>
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
            className="mt-1 flex items-center gap-2 rounded-xl border-t border-line px-2.5 py-2.5 text-sm font-semibold text-acc-ink hover:bg-sf2"
          >
            <Icon name="plus" size={18} /> Create an organisation
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
      className={`group relative flex items-center gap-3 rounded-xl px-3 py-2 text-[14.5px] font-medium transition-colors ${
        active ? "bg-side-2 text-side-ink" : "text-side-ink2 hover:bg-side-2/60 hover:text-side-ink"
      }`}
    >
      {active && <span className="absolute top-2 bottom-2 -left-4 w-1 rounded-r-full bg-mint" aria-hidden="true" />}
      <span className={active ? "text-mint" : ""}>
        <Icon name={item.icon} />
      </span>
      {item.label}
    </Link>
  );
}

function Group({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mt-6 first:mt-0">
      <div className="mb-1.5 truncate px-3 text-[11px] font-semibold tracking-[0.12em] text-side-ink2/70 uppercase">{title}</div>
      <div className="flex flex-col gap-0.5">{children}</div>
    </div>
  );
}

function AdminNav({ onNavigate }: { onNavigate: () => void }) {
  const items: Item[] = [
    { href: "/app/admin", label: "Overview", icon: "overview", exact: true },
    { href: "/app/admin/organisations", label: "Organisations", icon: "building" },
    { href: "/app/admin/people", label: "People", icon: "members" },
    { href: "/app/admin/keys", label: "API keys", icon: "keys" },
    { href: "/app/admin/audit", label: "Audit log", icon: "audit" },
  ];
  return (
    <nav>
      <Group title="Admin">
        {items.map((i) => (
          <NavLink key={i.href} item={i} onClick={onNavigate} />
        ))}
      </Group>
    </nav>
  );
}

function Nav({ onNavigate }: { onNavigate: () => void }) {
  const { current } = useAccount();
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
    <nav>
      <Group title="Workspace">
        {base.map((i) => (
          <NavLink key={i.href} item={i} onClick={onNavigate} />
        ))}
      </Group>
      {current && (
        <Group title={current.name}>
          {org.map((i) => (
            <NavLink key={i.href} item={i} onClick={onNavigate} />
          ))}
        </Group>
      )}
      <Group title="You">
        {personal.map((i) => (
          <NavLink key={i.href} item={i} onClick={onNavigate} />
        ))}
      </Group>
    </nav>
  );
}

function AccountMenu({ onSignOut }: { onSignOut: () => void }) {
  const { me } = useAccount();
  const [open, setOpen] = useState(false);
  const box = useClickAway(open, () => setOpen(false));
  if (!me) return null;
  const name = me.name || me.email.split("@")[0];
  return (
    <div ref={box} className="relative">
      <button onClick={() => setOpen(!open)} aria-expanded={open} aria-label="Account menu" className="flex items-center gap-2 rounded-full p-0.5 hover:ring-2 hover:ring-line">
        <Avatar name={name} size={34} />
      </button>
      {open && (
        <div className="fade-in absolute top-full right-0 z-40 mt-2 w-64 rounded-2xl border border-line bg-sf p-2 shadow-lift">
          <div className="flex items-center gap-3 px-2 py-2">
            <Avatar name={name} size={38} />
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold text-ink">{name}</div>
              <div className="truncate text-xs text-ink3">{me.email}</div>
            </div>
          </div>
          <div className="my-1 border-t border-line" />
          <div className="flex items-center justify-between px-2 py-1.5">
            <span className="text-sm text-ink2">Theme</span>
            <ThemeToggle />
          </div>
          {!me.is_staff && (
            <Link href="/app/profile" onClick={() => setOpen(false)} className="block rounded-xl px-2 py-2 text-sm text-ink hover:bg-sf2">
              Profile
            </Link>
          )}
          <button onClick={onSignOut} className="w-full rounded-xl px-2 py-2 text-left text-sm font-semibold text-false hover:bg-false-soft">
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}

function CreditsPill() {
  const { me, current } = useAccount();
  if (!me || me.is_staff) return null;
  const value = current ? current.balance : me.credits.balance;
  const low = value <= 10;
  return (
    <Link
      href={current ? (current.role === "owner" ? `/app/org/${current.id}/billing` : `/app/org/${current.id}`) : "/app/credits"}
      className={`tabular hidden items-center gap-2 rounded-full border px-3 py-1.5 text-sm font-semibold sm:inline-flex ${
        low ? "border-false/30 bg-false-soft text-false" : "border-line bg-sf text-ink hover:bg-sf2"
      }`}
      title={current ? `${current.name}'s credits` : "Your free credits"}
    >
      <span className={`h-2 w-2 rounded-full ${low ? "bg-false" : "bg-acc"}`} />
      {n(value)} credits
    </Link>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  const { me, loading } = useAccount();
  const [open, setOpen] = useState(false);
  const path = usePathname();
  const router = useRouter();
  const staff = !!me?.is_staff;
  useEffect(() => setOpen(false), [path]);
  // The admin account lives in the admin panel (it may open an organisation from
  // there); a user's pages are not for it. Users never reach the admin panel.
  useEffect(() => {
    if (loading || !me) return;
    const inAdmin = path.startsWith("/app/admin");
    if (staff && !inAdmin && !path.startsWith("/app/org/")) router.replace("/app/admin");
    if (!staff && inAdmin) router.replace("/app/check");
  }, [loading, me, staff, path, router]);

  async function signOut() {
    await authAction("logout").catch(() => undefined);
    try {
      localStorage.removeItem("fct_account");
    } catch {}
    window.location.href = "/";
  }

  const sidebar = (
    <div className="scroll-thin flex h-full flex-col gap-6 overflow-y-auto bg-side p-4 text-side-ink">
      <Link href={staff ? "/app/admin" : "/app/check"} className="flex items-center gap-2.5 px-1 pt-1 font-serif text-[1.6rem] font-semibold tracking-tight text-side-ink">
        <Seal size={34} /> Factify
      </Link>
      {staff ? (
        <div className="flex items-center gap-3 rounded-2xl border border-side-line bg-side-2 px-3 py-2.5">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-mint text-[#0b3d2d]">
            <Icon name="admin" size={18} />
          </span>
          <span>
            <span className="block text-sm font-semibold">Factify admin</span>
            <span className="block text-xs text-side-ink2">Full access</span>
          </span>
        </div>
      ) : (
        <Switcher onPick={() => setOpen(false)} />
      )}
      <div className="min-h-0 flex-1">{staff ? <AdminNav onNavigate={() => setOpen(false)} /> : <Nav onNavigate={() => setOpen(false)} />}</div>
      <div className="rounded-2xl border border-side-line bg-side-2 p-3">
        <div className="text-xs text-side-ink2">Theme</div>
        <div className="mt-2">
          <ThemeToggle onDark />
        </div>
      </div>
    </div>
  );

  return (
    <div className="min-h-dvh bg-bg lg:grid lg:grid-cols-[280px_minmax(0,1fr)]">
      <aside className="sticky top-0 hidden h-dvh lg:block">{sidebar}</aside>

      {open && (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Menu">
          <div className="absolute inset-0 bg-black/50 backdrop-blur-[2px]" onClick={() => setOpen(false)} />
          <div className="fade-in absolute inset-y-0 left-0 w-[86%] max-w-[300px] shadow-2xl">{sidebar}</div>
        </div>
      )}

      <div className="min-w-0">
        <header className="sticky top-0 z-30 border-b border-line/70 bg-bg/85 backdrop-blur-md">
          <div className="mx-auto flex h-16 max-w-[1240px] items-center gap-3 px-4 sm:px-6 lg:px-10">
            <button onClick={() => setOpen(true)} aria-label="Open menu" className="-ml-2 rounded-xl p-2 text-ink lg:hidden">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M4 7h16M4 12h10M4 17h16" />
              </svg>
            </button>
            <Link href={staff ? "/app/admin" : "/app/check"} className="flex items-center gap-2 font-serif text-xl font-semibold text-ink lg:hidden">
              <Seal size={28} /> <span className="hidden min-[380px]:inline">Factify</span>
            </Link>
            <div className="flex-1" />
            <CreditsPill />
            {!staff && (
              <Link href="/app/check" className="hidden items-center gap-1.5 rounded-full bg-acc px-3.5 py-1.5 text-sm font-semibold text-on-acc hover:brightness-110 md:inline-flex">
                <Icon name="bolt" size={16} /> New check
              </Link>
            )}
            <AccountMenu onSignOut={signOut} />
          </div>
        </header>

        <main className="px-4 py-7 sm:px-6 lg:px-10 lg:py-10">
          <div className="mx-auto max-w-[1240px]">
            {loading ? (
              <div className="flex items-center gap-2 py-20 text-ink2">
                <Spinner /> Loading…
              </div>
            ) : (
              <div className="fade-in">{children}</div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
