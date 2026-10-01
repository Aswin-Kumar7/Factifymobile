"use client";

// The browser's API client. Every call goes through /api/f (see app/api/f), which
// adds the session. The account in use (personal or an organisation) travels as
// X-Factify-Account, so its credits pay for the check.

export class ApiFailure extends Error {
  constructor(
    public status: number,
    message: string,
    public code?: string,
  ) {
    super(message);
  }
}

let currentAccount = "personal";
export function setAccount(account: string) {
  currentAccount = account;
}
export function getAccount() {
  return currentAccount;
}

function describe(status: number, body: unknown): string {
  const detail = (body as { detail?: unknown })?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return "Some of what you entered isn't valid. Check it and try again.";
  if (status === 401) return "Your session has ended. Sign in again.";
  if (status >= 500) return "Something went wrong on our side. Try again shortly.";
  return "That didn't work. Try again.";
}

export async function api<T = unknown>(
  path: string,
  init: RequestInit & { json?: unknown; account?: string } = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.json !== undefined) headers.set("content-type", "application/json");
  const account = init.account ?? currentAccount;
  if (account && account !== "personal") headers.set("x-factify-account", account);
  const response = await fetch(`/api/f${path}`, {
    ...init,
    headers,
    body: init.json !== undefined ? JSON.stringify(init.json) : init.body,
    cache: "no-store",
  });
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  let body: unknown = text;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    /* not JSON */
  }
  if (!response.ok && response.status !== 202) {
    if (response.status === 401 && typeof window !== "undefined" && !path.startsWith("/v1/auth")) {
      window.location.href = `/signin?next=${encodeURIComponent(window.location.pathname)}`;
    }
    throw new ApiFailure(
      response.status,
      describe(response.status, body),
      (body as { error_code?: string })?.error_code,
    );
  }
  return body as T;
}

export async function authAction(action: "login" | "register" | "logout" | "session" | "handoff", json?: unknown) {
  const response = await fetch(`/api/auth/${action}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(json ?? {}),
  });
  if (response.status === 204) return null;
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new ApiFailure(response.status, describe(response.status, body), body?.detail);
  return body;
}

// ---- types ----------------------------------------------------------------------

export type Me = {
  id: string;
  email: string;
  name: string | null;
  avatar_url: string | null;
  plan: string;
  joined_at: string | null;
  credits: { balance: number; used: number; checks: number; check_cost: number; limited: boolean };
  survey_due: boolean;
  is_staff: boolean;
  plan_usage?: PlanUsage | null;
};

/** A person's monthly plan and this month's use of it (contract 1.7). */
export type PlanUsage = {
  plan: "free" | "plus" | "pro";
  name: string;
  interval: "month" | "year" | null;
  renews_at: string | null;
  cancel_at_end: boolean;
  allowance: number;
  used: number;
  resets_at: string | null;
  credits: number;
  extra_enabled: boolean;
  extra_cap_paise: number | null;
  extra_used_paise: number;
  extra_price_paise: number;
  extra_blocked: boolean;
};

export type Role = "owner" | "developer" | "member";

export type MyOrg = {
  id: string;
  name: string;
  status: string;
  role: Role;
  monthly_limit: number | null;
  member_status: string;
  balance: number;
  my_month_spend: number;
};

export type Org = {
  id: string;
  name: string;
  billing_email: string | null;
  gst_number: string | null;
  status: string;
  monthly_spend_limit: number | null;
  shared_history: boolean;
  created_at: string;
  balance: number;
  held: number;
  month_spend: number;
  members: number;
  active_keys: number;
  my_role: Role;
  my_monthly_limit: number | null;
  alerts: { level: "error" | "warning"; text: string }[];
};

export type Member = {
  user_id: string;
  email: string;
  name: string | null;
  role: Role;
  monthly_limit?: number | null;
  status: string;
  joined_at: string;
  month_spend?: number;
  keys?: number;
  lifetime_spend?: number;
  last_active_at?: string | null;
};

export type ApiKey = {
  id: string;
  name: string;
  note: string | null;
  prefix: string;
  monthly_limit: number | null;
  ip_allowlist: string[];
  created_at: string;
  expires_at: string | null;
  last_used_at: string | null;
  revoked_at: string | null;
  replaced_by: string | null;
  created_by: string | null;
  created_by_email: string | null;
  month_spend: number;
  key?: string;
};

export type Usage = {
  by_day: { day: string; credits: number; checks: number }[];
  by_member: { user_id: string; email: string | null; credits: number; checks: number }[];
  by_key: { key_id: string; name: string; prefix: string; credits: number; checks: number }[];
  ledger: {
    created_at: string;
    delta: number;
    reason: string;
    note: string | null;
    email: string | null;
    key_name: string | null;
  }[];
};
