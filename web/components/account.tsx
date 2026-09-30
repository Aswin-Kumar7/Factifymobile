"use client";

// Who is signed in, their organisations, and which account pays for checks now
// ("personal" or an organisation's id). The choice is remembered in this browser.
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, Me, MyOrg, setAccount } from "@/lib/api";

type AccountState = {
  me: Me | null;
  orgs: MyOrg[];
  account: string;
  current: MyOrg | null;
  choose: (account: string) => void;
  refresh: () => Promise<void>;
  loading: boolean;
};

const Context = createContext<AccountState | null>(null);
const KEY = "fct_account";

export function AccountProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [orgs, setOrgs] = useState<MyOrg[]>([]);
  const [account, setAccountState] = useState("personal");
  const [loading, setLoading] = useState(true);

  const choose = useCallback((next: string) => {
    setAccount(next);
    setAccountState(next);
    try {
      localStorage.setItem(KEY, next);
    } catch {}
  }, []);

  const refresh = useCallback(async () => {
    const [who, mine] = await Promise.all([
      api<Me>("/v1/me", { account: "personal" }),
      api<MyOrg[]>("/v1/orgs", { account: "personal" }).catch(() => [] as MyOrg[]),
    ]);
    setMe(who);
    setOrgs(mine);
    let saved = "personal";
    try {
      saved = localStorage.getItem(KEY) || "personal";
    } catch {}
    if (saved !== "personal" && !mine.some((o) => o.id === saved)) saved = "personal";
    setAccount(saved);
    setAccountState((prev) => (prev === "personal" ? saved : mine.some((o) => o.id === prev) ? prev : "personal"));
  }, []);

  useEffect(() => {
    refresh().finally(() => setLoading(false));
  }, [refresh]);

  const current = orgs.find((o) => o.id === account) ?? null;
  return (
    <Context.Provider value={{ me, orgs, account, current, choose, refresh, loading }}>{children}</Context.Provider>
  );
}

export function useAccount() {
  const value = useContext(Context);
  if (!value) throw new Error("useAccount outside AccountProvider");
  return value;
}
