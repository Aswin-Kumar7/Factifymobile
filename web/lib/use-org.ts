"use client";

import { useCallback, useEffect, useState } from "react";
import { useAccount } from "@/components/account";
import { api, Org } from "./api";

/** An organisation's details, loaded by id; opening its pages makes it the account in use. */
export function useOrg(id: string) {
  const { account, choose } = useAccount();
  const [org, setOrg] = useState<Org | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      setOrg(await api<Org>(`/v1/orgs/${id}`, { account: "personal" }));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [id]);

  useEffect(() => {
    if (account !== id) choose(id);
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  return { org, error, reload };
}
