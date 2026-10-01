"use client";

// The dashboard's frame: a sidebar (a drawer on phones) with the workspace, the
// pages, this month's checks and the account, and a slim top bar with where you
// are and the theme. The admin account gets its own sidebar; everyone else never
// sees an admin link.

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { authAction } from "@/lib/api";
import { n, roleName } from "@/lib/format";
import { useAccount } from "./account";
import { ThemeButton } from "./theme";
import { Avatar, Seal, Spinner } from "./ui";

type Item = { href: string; label: string; icon: keyof typeof icons; exact?: boolean };

const icons = {
  check: "M8.5 12.2l2.4 2.4 4.6-4.9M20.5 12a8.5 8.5 0 11-17 0 8.5 8.5 0 0117 0z",
  history: "M12 8v4.5l3 1.8M4 12a8 8 0 102.3-5.6M4 4.5v3.6h3.6",
  credits: "M3.5 6h17v12h-17zM3.5 10h17",
  overview: "M4 19.5h16M7 16V11M12 16V6.5M17 16v-3.5",
  members: "M9 12a3 3 0 100-6 3 3 0 000 6zM3.5 18.5c.6-3 2.8-4.5 5.5-4.5s4.9 1.5 5.5 4.5M16 6.5a3 3 0 010 5.6M17.5 14.3c1.6.6 2.7 2 3 4.2",
  keys: "M15 7a4 4 0 11-3.9 4.9L3 20v-3h3v-3h3l2.1-2.1A4 4 0 0115 7z",
  usage: "M3 3v18h18M7 15l4-4 3 3 5-6",
  billing: "M3 7h18v12H3zM3 11h18M7 15h4",
  settings: "M12 15a3 3 0 100-6 3 3 0 000 6zM19.4 13.5l1.4 1.1-1.8 3.1-1.7-.6a7 7 0 01-2 1.2L15 20h-3.6l-.3-1.7a7 7 0 01-2-1.2l-1.7.6-1.8-3.1 1.4-1.1a7 7 0 010-2.4l-1.4-1.1 1.8-3.1 1.7.6a7 7 0 012-1.2L11.4 4H15l.3 1.7a7 7 0 012 1.2l1.7-.6 1.8 3.1-1.4 1.1a7 7 0 010 2.4z",
  audit: "M7 4h8l3 3v13H7zM10 10h5M10 13.5h5M10 17h3",
  admin: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6l8-3z",
  plus: "M12 5v14M5 12h14",
  building: "M4.5 20V6.5L12 4v16M12 9h7.5v11M3 20h18M7.5 9h1.5M7.5 12.5h1.5M7.5 16h1.5M15 12.5h1.5M15 16h1.5",
  bolt: "M13 2L4 14h7l-1 8 9-12h-7l1-8z",
  logout: "M14 5H6.5A1.5 1.5 0 005 6.5v11A1.5 1.5 0 006.5 19H14M10 12h10M16.5 8.5L20 12l-3.5 3.5",
  help: "M9.7 9.5a2.4 2.4 0 014.6 1c0 1.6-2.3 2-2.3 3.5M12 16.8v.2M20.5 12a8.5 8.5 0 11-17 0 8.5 8.5 0 0117 0z",
};

export function Icon({ name, size = 18 }: { name: keyof typeof icons; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
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

/** Which account pays: yourself, or one of your organisations. */
function Switcher({ onPick }: { onPick: () => void }) {
  const { orgs, account, current, choose } = useAccount();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const box = useClickAway(open, () => setOpen(false));
  const label = current ? current.name : "Personal";
  const options = [{ id: "personal", name: "Personal", note: "Your own plan" }, ...orgs.map((o) => ({ id: o.id, name: o.name, note: roleName[o.role] }))];
  return (
    <div ref={box} className="relative">
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-label={`Workspace: ${label}. Switch workspace`}
        className="flex w-full items-center gap-2.5 rounded-[9px] border border-side-line px-2 py-1.5 text-left transition-colors hover:bg-side-2"
      >
        <span className="flex h-6.5 w-6.5 shrink-0 items-center justify-center rounded-[7px] bg-acc-soft text-xs font-semibold text-acc-ink">
          {label.slice(0, 1).toUpperCase()}
        </span>
        <span className="min-w-0 flex-1 truncate text-[13.5px] font-medium text-side-ink">{label}</span>
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" className="text-side-ink2" aria-hidden="true">
          <path d="M5 6l3-3 3 3M5 10l3 3 3-3" />
        </svg>
      </button>
      {open && (
        <div role="listbox" className="fade-in absolute top-full right-0 left-0 z-40 mt-1.5 rounded-xl border border-line2 bg-sf p-1.5 shadow-lift">
          <div className="eyebrow px-2.5 pt-1.5 pb-1">Check and pay as</div>
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
              className={`flex w-full items-center gap-3 rounded-lg px-2.5 py-2 text-left text-sm hover:bg-hover ${account === o.id ? "bg-hover" : ""}`}
            >
              <Avatar name={o.name} size={28} />
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium text-ink">{o.name}</span>
                <span className="block truncate text-xs text-ink3">{o.note}</span>
              </span>
              {account === o.id && <span className="text-acc-ink">✓</span>}
            </button>
          ))}
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
      className={`flex h-9 items-center gap-3 rounded-lg px-2.5 text-sm transition-colors ${
        active ? "bg-acc-soft text-side-ink [&_svg]:text-acc-ink" : "text-side-ink2 hover:bg-side-2 hover:text-side-ink"
      }`}
    >
      <Icon name={item.icon} />
      <span className="truncate">{item.label}</span>
    </Link>
  );
}

function Group({ title, children }: { title?: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      {title && <div className="eyebrow truncate px-2.5 pb-1.5 text-[11px]">{title}</div>}
      {children}
    </div>
  );
}

function AdminNav({ onNavigate }: { onNavigate: () => void }) {
  const items: Item[] = [
    { href: "/app/admin", label: "Overview", icon: "overview", exact: true },
    { href: "/app/admin/requests", label: "Requests", icon: "plus" },
    { href: "/app/admin/organisations", label: "Organisations", icon: "building" },
    { href: "/app/admin/people", label: "People", icon: "members" },
    { href: "/app/admin/keys", label: "API keys", icon: "keys" },
    { href: "/app/admin/audit", label: "Audit log", icon: "audit" },
  ];
  return (
    <Group>
      {items.map((i) => (
        <NavLink key={i.href} item={i} onClick={onNavigate} />
      ))}
    </Group>
  );
}

function Nav({ onNavigate }: { onNavigate: () => void }) {
  const { current } = useAccount();
  const base: Item[] = [
    { href: "/app/check", label: "Check", icon: "check", exact: true },
    { href: "/app/history", label: "History", icon: "history" },
    { href: "/app/credits", label: "Plan & usage", icon: "credits" },
  ];
  const org: Item[] = [];
  if (current) {
    const o = `/app/org/${current.id}`;
    org.push({ href: o, label: "Overview", icon: "overview", exact: true });
    org.push({ href: `${o}/members`, label: "Members", icon: "members" });
    if (current.role !== "member") org.push({ href: `${o}/keys`, label: "API keys", icon: "keys" });
    org.push({ href: `${o}/usage`, label: "Usage", icon: "usage" });
    if (current.role === "owner") {
      org.push({ href: `${o}/billing`, label: "Plan & billing", icon: "billing" });
      org.push({ href: `${o}/settings`, label: "Settings", icon: "settings" });
      org.push({ href: `${o}/audit`, label: "Audit log", icon: "audit" });
    }
  }
  return (
    <nav className="flex flex-col gap-5" aria-label="Pages">
      <Group>
        {base.map((i) => (
          <NavLink key={i.href} item={i} onClick={onNavigate} />
        ))}
      </Group>
      {current ? (
        <Group title={current.name}>
          {org.map((i) => (
            <NavLink key={i.href} item={i} onClick={onNavigate} />
          ))}
        </Group>
      ) : (
        <Group title="Team">
          <NavLink item={{ href: "/app/org/new", label: "Create an organisation", icon: "members" }} onClick={onNavigate} />
        </Group>
      )}
    </nav>
  );
}

/** This month's checks, as the app's dark feature card. */
function MonthMeter({ onNavigate }: { onNavigate: () => void }) {
  const { me, current } = useAccount();
  if (!me) return null;
  if (current) {
    return (
      <Link href={`/app/org/${current.id}`} onClick={onNavigate} className="block rounded-[11px] border border-hero-line bg-hero p-3 text-hero-ink">
        <span className="flex justify-between gap-2 text-[13px] text-hero-ink2">
          <span className="truncate">{current.name}</span>
          <span className="tabular font-medium text-hero-ink">{n(current.balance)}</span>
        </span>
        <span className="mt-1 block text-xs text-hero-ink2">credits in the pool · you used {n(current.my_month_spend)} this month</span>
      </Link>
    );
  }
  const p = me.plan_usage;
  const total = p?.allowance ?? 0;
  const used = Math.min(p?.used ?? 0, total);
  const reset = p?.resets_at ? new Date(p.resets_at).toLocaleDateString("en-IN", { day: "numeric", month: "short" }) : null;
  return (
    <Link href="/app/credits" onClick={onNavigate} className="block rounded-[11px] border border-hero-line bg-hero p-3 text-hero-ink">
      <span className="flex items-baseline justify-between text-[13px] text-hero-ink2">
        <span>Checks this month</span>
        <span className="tabular font-medium text-hero-ink">
          {n(used)} <span className="font-normal text-hero-ink2">/ {n(total)}</span>
        </span>
      </span>
      <span className="my-2.5 block h-1 overflow-hidden rounded-full bg-hero-line">
        <span className="block h-full rounded-full bg-hero-acc" style={{ width: `${total ? Math.max(2, (used / total) * 100) : 0}%` }} />
      </span>
      <span className="flex justify-between text-xs text-hero-ink2">
        <span>{reset ? `Resets on ${reset}` : "Resets on the 1st"}</span>
        {(p?.credits ?? 0) > 0 && <span className="tabular">+{n(p?.credits)} credits</span>}
      </span>
    </Link>
  );
}

function Me({ staff, onSignOut }: { staff: boolean; onSignOut: () => void }) {
  const { me } = useAccount();
  if (!me) return null;
  const name = me.name || me.email.split("@")[0];
  return (
    <div className="flex items-center gap-2.5 rounded-[10px] p-1.5">
      <Avatar name={name} size={32} />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[13.5px] font-medium text-side-ink">{name}</span>
        <span className={`block truncate text-xs ${staff ? "text-mis" : "text-acc-ink"}`}>{staff ? "Admin" : `${me.plan_usage?.name ?? "Free"} plan`}</span>
      </span>
      {staff ? (
        <button onClick={onSignOut} aria-label="Log out" title="Log out" className="flex h-8 w-8 items-center justify-center rounded-lg text-side-ink2 hover:bg-side-2 hover:text-side-ink">
          <Icon name="logout" size={17} />
        </button>
      ) : (
        <Link href="/app/profile" aria-label="Settings" title="Settings" className="flex h-8 w-8 items-center justify-center rounded-lg text-side-ink2 hover:bg-side-2 hover:text-side-ink">
          <Icon name="settings" size={17} />
        </Link>
      )}
    </div>
  );
}

const titles: [RegExp, string][] = [
  [/^\/app\/check/, "Check"],
  [/^\/app\/history/, "History"],
  [/^\/app\/credits/, "Plan & usage"],
  [/^\/app\/profile/, "Settings"],
  [/^\/app\/org\/new/, "Create an organisation"],
  [/^\/app\/org\//, "Organisation"],
  [/^\/app\/admin\/requests/, "Requests"],
  [/^\/app\/admin\/organisations/, "Organisations"],
  [/^\/app\/admin\/people/, "People"],
  [/^\/app\/admin\/keys/, "API keys"],
  [/^\/app\/admin\/audit/, "Audit log"],
  [/^\/app\/admin/, "Overview"],
];

export function Shell({ children }: { children: React.ReactNode }) {
  const { me, loading, current } = useAccount();
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

  const close = () => setOpen(false);
  const sidebar = (
    <div className="scroll-thin flex h-full flex-col gap-4 overflow-y-auto border-r border-side-line bg-side px-3 py-4 text-side-ink">
      <div className="flex items-center gap-2 px-2 py-1">
        <Link href={staff ? "/app/admin" : "/app/check"} className="flex items-center gap-2 text-base font-semibold tracking-tight text-side-ink" aria-label="Factify home">
          <Seal size={22} /> Factify
        </Link>
        {staff && <span className="ml-auto rounded-md bg-mis-soft px-2 py-0.5 text-xs font-medium text-mis">Admin</span>}
      </div>
      {!me ? (
        // Until we know who this is, neither a person's nor the admin's pages.
        <div className="h-[86px]" aria-hidden="true" />
      ) : staff ? (
        <div className="flex items-center gap-2.5 rounded-[9px] border border-side-line px-2.5 py-2">
          <span className="text-mis">
            <Icon name="admin" />
          </span>
          <span>
            <span className="block text-[13.5px] font-medium">Factify admin</span>
            <span className="block text-xs text-side-ink2">Platform staff</span>
          </span>
        </div>
      ) : (
        <>
          <Switcher onPick={close} />
          <Link href="/app/check?new=1" onClick={close} className="flex h-10 items-center justify-center gap-2 rounded-[10px] bg-acc text-sm font-medium text-on-acc transition-colors hover:bg-acc-h">
            <Icon name="plus" size={15} /> New check
          </Link>
        </>
      )}
      <div className="min-h-0 flex-1">{!me ? null : staff ? <AdminNav onNavigate={close} /> : <Nav onNavigate={close} />}</div>
      <div className="flex flex-col gap-2">
        {me && !staff && <MonthMeter onNavigate={close} />}
        <Me staff={staff} onSignOut={signOut} />
      </div>
    </div>
  );

  const title = titles.find(([re]) => re.test(path))?.[1] ?? "";
  const where = !me ? "" : staff ? "Admin" : current ? current.name : "Personal";

  return (
    <div className="min-h-dvh bg-bg lg:grid lg:grid-cols-[260px_minmax(0,1fr)]">
      <aside className="sticky top-0 hidden h-dvh lg:block">{sidebar}</aside>

      {open && (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Menu">
          <div className="absolute inset-0 bg-black/50 backdrop-blur-[2px]" onClick={close} />
          <div className="fade-in absolute inset-y-0 left-0 w-[86%] max-w-[280px] shadow-2xl">{sidebar}</div>
        </div>
      )}

      <div className="min-w-0">
        <header className="sticky top-0 z-30 border-b border-line bg-bg/85 backdrop-blur-md">
          <div className="flex h-14 items-center gap-3 px-4 sm:px-7">
            <button onClick={() => setOpen(true)} aria-label="Open menu" className="-ml-1.5 rounded-lg p-1.5 text-ink lg:hidden">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
                <path d="M4 7h16M4 12h10M4 17h16" />
              </svg>
            </button>
            <div className="flex min-w-0 items-center gap-2 text-sm text-ink3">
              <span className="hidden truncate sm:inline">{where}</span>
              <span className="hidden sm:inline">/</span>
              <span className="truncate text-ink">{title}</span>
            </div>
            <div className="flex-1" />
            <a href="mailto:aswin.aswin5640@gmail.com" aria-label="Help" title="Help" className="hidden h-9 w-9 items-center justify-center rounded-lg text-ink2 hover:bg-hover hover:text-ink sm:inline-flex">
              <Icon name="help" />
            </a>
            <ThemeButton />
          </div>
        </header>

        <main className="px-4 py-7 sm:px-8 lg:py-9">
          <div className="mx-auto max-w-[1100px]">
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
