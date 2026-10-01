"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { use, useEffect, useState } from "react";
import { Avatar, Badge, TabLinks } from "@/components/ui";
import { api, Org } from "@/lib/api";
import { when } from "@/lib/format";

export default function AdminOrgLayout({ children, params }: { children: React.ReactNode; params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const path = usePathname();
  const [org, setOrg] = useState<Org | null>(null);
  useEffect(() => {
    api<Org>(`/v1/orgs/${id}`, { account: "personal" }).then(setOrg).catch(() => undefined);
  }, [id, path]);
  const base = `/app/admin/organisations/${id}`;
  const tabs = [
    { href: base, label: "Overview" },
    { href: `${base}/members`, label: "Members", count: org?.members },
    { href: `${base}/keys`, label: "API keys", count: org?.active_keys },
    { href: `${base}/usage`, label: "Usage" },
    { href: `${base}/billing`, label: "Billing" },
    { href: `${base}/settings`, label: "Settings" },
    { href: `${base}/audit`, label: "Audit log" },
  ];
  return (
    <>
      <Link href="/app/admin/organisations" className="mb-4 inline-flex items-center gap-1 text-sm font-semibold text-ink3 hover:text-ink">
        ← All organisations
      </Link>
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center">
        <Avatar name={org?.name ?? "…"} size={56} />
        <div className="min-w-0 flex-1">
          <div className="text-xs font-semibold tracking-[0.12em] text-acc-ink uppercase">Organisation · admin view</div>
          <h1 className="truncate text-[2rem] leading-tight font-medium tracking-tight text-ink sm:text-[2.4rem]">{org?.name ?? "…"}</h1>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-ink3">
            {org && <Badge tone={org.status === "active" ? "acc" : "bad"}>{org.status}</Badge>}
            {org?.billing_email && <span>{org.billing_email}</span>}
            {org && <span>· created {when(org.created_at)}</span>}
          </div>
        </div>
      </div>
      <TabLinks tabs={tabs} active={path} />
      {children}
    </>
  );
}
