// Readable words for every action the server writes to the audit log
// (app/orgs/store.py, app/api/*): an organisation's own log and the admin's.

const words: Record<string, string> = {
  "org.created": "Created the organisation",
  "org.updated": "Changed settings",
  "org.closed": "Closed the organisation",
  "member.updated": "Changed a member",
  "member.removed": "Removed a member",
  "member.joined_by_domain": "Joined through the verified domain",
  "invite.created": "Invited",
  "invite.revoked": "Withdrew an invitation",
  "invite.accepted": "Accepted an invitation",
  "key.created": "Created an API key",
  "key.updated": "Changed an API key",
  "key.rotated": "Rotated an API key",
  "key.revoked": "Revoked an API key",
  "credits.purchase": "Bought credits",
  "credits.grant": "Factify added credits",
  "credits.adjustment": "Factify adjusted credits",
  "credits.personal_purchase": "Bought personal credits",
  "domain.added": "Added a domain",
  "domain.updated": "Changed a domain",
  "domain.removed": "Removed a domain",
  "plan.subscribe_started": "Started paying for a plan",
  "plan.started": "Plan started",
  "plan.changed": "Changed how the organisation pays",
  "plan.extra_usage": "Changed extra usage",
  "plan.cancelling": "Cancelled the plan (ends with its period)",
  "plan.cancelled": "Plan cancelled",
  "plan.halted": "Plan stopped: a renewal payment failed",
  "org_request.created": "Asked for an organisation plan",
  "admin.org_suspended": "Factify suspended the organisation",
  "admin.org_active": "Factify restored the organisation",
  "admin.org_request_approved": "Factify approved an organisation request",
  "admin.org_request_rejected": "Factify rejected an organisation request",
  "admin.user_credits": "Factify changed a person's credits",
  "admin.user_disabled": "Factify disabled a person",
  "admin.user_enabled": "Factify enabled a person",
};

const planNames: Record<string, string> = { plus: "Plus", pro: "Pro", team: "Team", api: "Pay per check", credits: "Credit packs" };

/** The action in words; an unknown one (a newer server) as it was written. */
export function auditAction(action: string) {
  if (words[action]) return words[action];
  const [group, rest] = action.split(".");
  return rest ? `${group.replace(/_/g, " ")}: ${rest.replace(/_/g, " ")}` : action;
}

function value(key: string, v: unknown): string {
  if (key === "plan" && typeof v === "string") return planNames[v] ?? v;
  if (key.endsWith("_paise") && typeof v === "number") return `₹${(v / 100).toLocaleString("en-IN")}`;
  if (typeof v === "boolean") return v ? "on" : "off";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

/** The details of an entry as "key: value" pairs, readable. */
export function auditDetail(detail: Record<string, unknown> | null | undefined) {
  return Object.entries(detail || {})
    .filter(([, v]) => v !== null && v !== "")
    .map(([k, v]) => `${k.replace(/_paise$/, "").replace(/_/g, " ")}: ${value(k, v)}`)
    .join(", ");
}
