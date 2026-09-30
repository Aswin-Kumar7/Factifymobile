"use client";

import { use } from "react";
import { OrgOverview } from "@/components/org-overview";
import { Badge, Notice, PageTitle, Spinner } from "@/components/ui";
import { roleName } from "@/lib/format";
import { useOrg } from "@/lib/use-org";

export default function Overview({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { org, error } = useOrg(id);
  if (error) return <Notice tone="error">{error}</Notice>;
  if (!org) return <Spinner />;
  return (
    <>
      <PageTitle
        eyebrow="Organisation"
        title={org.name}
        action={<Badge tone={org.my_role === "owner" ? "acc" : "neutral"}>{roleName[org.my_role]}</Badge>}
      />
      <OrgOverview id={id} base={`/app/org/${id}`} />
    </>
  );
}
