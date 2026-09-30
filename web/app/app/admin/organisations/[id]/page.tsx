"use client";

import { use } from "react";
import { OrgOverview } from "@/components/org-overview";

export default function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return <OrgOverview id={id} admin base={`/app/admin/organisations/${id}`} />;
}
