# Factify website and dashboard: plan

Written 2026-09-30. Status: built 2026-09-30 (section 12); decisions in section 11.

The website has three parts:

1. **Landing page**: public; a first, placeholder design.
2. **Dashboard**: everyone signed in can check things there as they do in the app,
   with the same account and the same 100 free credits.
3. **Organisations**: a paying master account (the org owner) with sub-accounts
   (members), one shared credit pool, per-member limits, API keys for the check
   endpoints, and a panel to manage all of it. Plus an **admin panel** for us, the
   Factify team.

## 1. How others do it (researched 2026-09-30)

| Product | Structure | Keys | Credits and limits |
|---|---|---|---|
| Anthropic Console | Org → workspaces (a default one that can't be deleted) | Scoped to a workspace; service-account keys outlive their creator | Prepaid org credits; each workspace can have spend and rate limits **lower than** the org's; out of spend → 429 + `error_code` |
| OpenAI Platform | Org → projects; roles Owner/Reader, project Owner/Member/Viewer | Project keys; service accounts; admins can restrict which key types exist | Prepaid credits with auto-recharge; hard spend limits per org and project |
| Tavily | Single account | Plain keys | 1 credit per basic search, 2 per advanced; `usage.credits` in each response; own codes 432/433 for plan and spend limits |
| Stripe | Account (+ orgs) | `sk_live_`/`rk_` prefixes, **shown once**, restricted scopes, rotation with up to 7 days of overlap, IP allowlist, per-key request log | `Idempotency-Key` on POST, replayed for 24 h |
| Google Cloud | Billing account → projects | n/a | Budgets alert at 50/90/100% but **do not stop** spending |
| WorkOS / Clerk / Auth0 | n/a | n/a | Enterprise SSO (SAML/OIDC) at about $75–150 per connection per month; DNS TXT domain verification; JIT membership; SCIM as an add-on |

Sources: platform.claude.com/docs (workspaces, admin-api, rate-limits),
developers.openai.com (rbac, spend-limits, rate-limits), docs.tavily.com
(api-credits, search), docs.stripe.com (keys, idempotent_requests),
docs.cloud.google.com (budgets), workos.com (pricing, domain-verification, JIT),
github.blog (token formats), GitHub secret scanning partner program docs.

**What we take from them:**

- **Structure:** bill at the org, and let the owner set lower limits under it.
- **Keys:** a few fixed roles, not custom ones. Keys are shown once, stored hashed, and
  carry a recognisable prefix and a checksum.
- **Metering and errors:** every response says what it cost. Out-of-credit has its own
  error, separate from rate limits. Credits are held before the work and settled after,
  so nobody can overspend by sending requests at the same time.
- **Alerts:** they notify people. Only limits stop traffic.

## 2. Who uses it

| Who | What they can do |
|---|---|
| **Free user** (anyone signed in) | Check text, links, pictures, videos and PDFs on the web; see their credits and history. 100 free credits, shared with the phone app. **No API keys.** |
| **Org owner** (master account, pays) | Everything a member can do, plus: set up the org, buy credits, invite and remove members, set each member's monthly credit limit, let a member create API keys, create and revoke any key, see all usage, invoices and the audit log. |
| **Org developer** (member allowed to use API keys) | Web checks from the org pool within their limit; create, rotate and revoke **their own** keys; see their own usage. |
| **Org member** | Web checks from the org pool within their limit; see their own usage. No keys. |
| **Factify admin** (us) | See and manage every org, user and key; grant or adjust credits with a reason; suspend orgs or users; revoke leaked keys; see platform usage and provider costs; the review queue; survey results. |

An org can have **more than one owner**, so that if one person leaves, the org is
not locked out. At least one owner must always remain. A later "Billing" role (sees
invoices only) and "Admin" role (manages members, not billing) are easy to add.

One person can belong to their personal account and to an org at once. The dashboard
has an **account switcher** ("Personal · Acme News"), and the credits a check uses
come from whichever account is selected.

## 3. Credits

### Accounts and pools

- A **credit account** is either personal (one per user, 100 free on sign-up, as
  today) or an org pool. The ledger (0003) is generalised: each entry names the
  account it draws on, **who** spent it, and the **API key** if one was used.
- **Org pool:** the owner buys credits into it. Every web check by a member and every
  API call by an org key draws from it.
- **Member limit:** optional, credits per calendar month (e.g. 2,000). A key's spend
  counts against the member who created it.
- **Key limit:** optional, credits per month, for a key used by one integration.
- **Org spend limit:** optional, credits per month, as a safety cap below the pool.

### Hold, then settle (no overspend)

The app today checks the balance, runs the check, then charges. That is fine for one
phone, but 50 parallel API calls would all pass the balance check. So:

1. **Hold:** in one database transaction, lock the pool and the member row, check
   `balance − held ≥ cost`, the member's month-to-date spend plus holds against their
   limit, and the key's limit; if all pass, insert a hold row. Otherwise refuse (§4).
2. **Run the check.**
3. **Settle:** turn the hold into a ledger charge. If the check failed, release the
   hold; **failed checks are never charged** (as today).
4. Holds expire after 15 minutes, so a crashed worker never locks credits.

### What a check costs

Today every check costs 1 credit. A price table (in code, shown in the docs):

| Check | Proposed credits |
|---|---|
| Text or link | 1 |
| Picture or PDF | 1 |
| Video (speech read, frames checked) | 3 (decision) |
| Answered from the cache (the same claim checked before) | 1 or 0 (decision) |

Every response carries `usage: {"credits": n}` and a
`Factify-Credits-Remaining` header.

### Alerts

- **Owners** get an email at 50%, 80% and 100% of the pool, and when any member
  reaches 90% of their limit.
- **Members** see their own limit in the dashboard.
- **Later:** auto top-up (a threshold and an amount), once payments exist.

## 4. The API

**Endpoints:** the same checks as the app.

- `POST /v1/verify` for text or a link
- `POST /v1/verify/file` for a picture, PDF or video
- `GET /v1/cases/{id}` and `GET /v1/cases/{id}/events` to follow a check

They accept either the app's session **or** an API key:

```
Authorization: Bearer fct_live_3kQ9...Xz_7Hc2aB
```

**Key format.** `fct_live_` (or `fct_test_`) + 32 random characters + a 6-character
checksum, following GitHub's format:

- Scanners can recognise it, and a mistyped key fails without touching the database.
- We store only its SHA-256 and the first 12 characters, which are shown for recognition.
- The full key is shown **once**, on creation.
- Each key has: a name, a note ("where it is used"), who created it, when it was last
  used, an optional expiry, an optional monthly limit, and an optional IP allowlist.
- **Rotate:** a new key is issued, and the old one keeps working for 24 hours.

**Errors:** each has its own status and a machine-readable `error_code`.

| Status | `error_code` | When |
|---|---|---|
| 401 | `invalid_api_key` | Unknown, mistyped, revoked or expired key |
| 403 | `key_not_allowed` | Free account, suspended member or org, or IP not allowed |
| 402 | `insufficient_credits` | The pool can't pay for this check |
| 402 | `member_limit_reached` / `key_limit_reached` / `org_spend_limit_reached` | A monthly limit is reached (no `Retry-After`) |
| 429 | `rate_limited` | Too many requests (with `Retry-After` and the `RateLimit` headers) |

We keep 402 for credits because the app already uses it. Every body names the
`error_code`.

**Other API features:**

- **Rate limits:** a token bucket per key (e.g. 60 checks a minute) and per org,
  separate from credits.
- **Idempotency:** an `Idempotency-Key` on a POST replays the first answer for 24 hours
  and never charges twice, so a network retry is safe.
- **Docs:** a public page generated from the OpenAPI schema FastAPI already makes,
  covering the key-accessible endpoints only, with the price table and examples in
  curl, Python and JavaScript.
- **Later:** join GitHub's secret-scanning partner programme, so a key pushed to a
  public repository is revoked automatically and the owner is told.

## 5. The screens

### Public
- **Landing (placeholder design):**
  - Hero: "Know what's true before you share it".
  - How it works: paste, check, sources.
  - What it checks: text, links, pictures, videos, voice.
  - For newsrooms and teams: API, shared credits.
  - Pricing: Free 100, Organisation (contact or packs).
  - App download, sign in.
- **Privacy** (moves here from the API), **Terms**, **API docs**.

### Everyone signed in
- **Check**: paste text or a link, or upload a picture, PDF or video; follow it live;
  the result with verdict, sources and advisories, like the app.
- **History**: past checks.
- **Credits**: balance, what each check used.
- **Profile**: name, email, sign-in method, sign out.
- **Free users only:** "Create an organisation".

### Org developer and member
- **Usage**: their own spend this month against their limit.
- **API keys**: developers only; their own keys.

### Org owner
- **Overview**: pool balance, spend this month, trend, top members, top keys, alerts.
- **Members**:
  - Invite by email, with a role and a monthly limit. Invites expire in 21 days.
  - Change a member's role or limit, suspend them, or remove them. Removing a member
    asks what to do with their keys: revoke them (the default) or move them to an owner.
- **API keys**: every key in the org. Create, rotate, revoke, set limits, see last use.
- **Usage**: by day, by member and by key, with CSV export.
- **Billing**: buy credits, invoices, alerts; auto top-up later.
- **Settings**: org name, billing email, GST number, verified domain (later),
  SSO (later), transfer ownership, close the org.
- **Audit log**: who invited whom, key created or revoked, limits changed, credits bought.

### Factify admin (us)
- **Orgs**: search; status and plan; detail with members, pool and keys; grant or adjust
  credits (a reason is required and logged); suspend or restore.
- **Users**: search, grant credits, disable, see their orgs.
- **Keys**: search by prefix; revoke.
- **Platform**:
  - Checks per day, credits used and sold.
  - Provider cost (search, AI model) against credits, to see our margin.
  - Server health.
  - The existing review queue (`/v1/review`).
  - Survey results, e.g. how many people are journalists.
- **Access**: staff accounts only, set in the database, never self-granted. Every admin
  action goes into the audit log.

## 6. Sign-in and SSO

- **Phase 1:** the existing accounts (email + password, Google) work on the web
  too. People join an org **by invitation**.
- **Phase 2:** an owner verifies their domain (DNS TXT record). Anyone signing in with an
  email at that domain can then join the org as a member, with a default role and limit
  (JIT). A Google Workspace domain can be required.
- **Phase 3, when a paying org asks:** SAML/OIDC single sign-on through WorkOS or Clerk
  (about $75–125 per connection per month, passed on in that org's price), and later
  SCIM so their IT adds and removes people automatically. At least one owner keeps a
  password or Google sign-in, as Supabase requires, so a broken SSO setup can't lock
  the org out.

## 7. Payments

- **Now:** Razorpay in test mode (decided): UPI, cards and net banking, with GST
  invoices. Stripe's onboarding for Indian businesses is harder. Credit packs, e.g.
  5,000 / 20,000 / 100,000. Razorpay Checkout on the Billing page, a signed webhook that
  adds the credits once payment is captured (and never twice for one payment), and
  downloadable invoices. A Factify admin can also add credits by hand (logged).
- **After KYC:** swap the test keys for live keys; nothing else changes.
- **Phase 3:** auto top-up. If a recharge fails, the owner is emailed and checks stop
  at 0.

## 8. Privacy

The app and the privacy policy promise that what someone checks is **not linked to
their account**. The web must keep that promise:

- **Personal history** is kept **in the browser** (IndexedDB), as the phone keeps it on
  the phone.
- **Org history:** organisations often want a shared record of checks for audits. That
  needs an **opt-in** setting chosen by the org owner, stated in the privacy policy, and
  applying to org checks only (decision).
- Usage records hold who, when, which key and how many credits, never the content.

## 9. How it is built

- **Web app:** Next.js (App Router, TypeScript), Tailwind and shadcn/ui, in `web/`.
  The landing page is server-rendered so search engines read it, and the dashboard is
  client-side against the existing API. The app's colours, fonts (Newsreader, Geist)
  and seal are reused.
- **Web sign-in:** the API's session token kept in an httpOnly cookie through a Next.js
  route handler, never in `localStorage`.
- **Deploy:** a third container on the same VM. Caddy sends `/v1/*` to the API and
  everything else to the web app. There is room: the VM has 16 GB, and the server uses
  about 6 GB. A real domain (e.g. `factify.in`) is needed before SSO, payments and the
  Google logo. It also replaces the Azure address in the app, Google's settings and
  the privacy page.
- **Server:**
  - Migrations 0006+: `organisation`, `org_member`, `org_invite`, `credit_account`,
    `credit_hold`, `api_key`, `idempotency`, and `app_user.is_staff`.
  - The ledger gains `account_id`, `api_key_id`, `kind`.
  - New routers: `/v1/orgs`, `/v1/keys`, `/v1/usage`, `/v1/admin`.
  - Key auth in `signed_in()`.
  - The credit book's `authorize`/`charge` become `hold`/`settle`.
  - Credit enforcement is always on for keys and orgs. Personal accounts turn it on
    when plans exist.
- **Tests:**
  - Concurrency: 50 parallel requests against a 10-credit pool → exactly 10 run.
  - Limits and roles: every role against every action.
  - Keys: format, checksum and revocation.
  - Idempotent replay.
  - The web: Playwright on the main paths.

## 10. Order of work

| Phase | What | Rough size |
|---|---|---|
| **A. Server foundations** | Orgs, members, invites, credit accounts, hold/settle, API keys, key auth, limits, error codes, usage and admin endpoints, audit log; tests | 3–4 days |
| **B. Web: landing + check** | Next.js app, placeholder landing, sign-in (email + Google), Check, History (browser), Credits, Profile; deploy behind Caddy | 3 days |
| **C. Org dashboard** | Create org, switcher, Overview, Members, Keys, Usage, Settings, Audit | 3–4 days |
| **D. Admin panel** | Orgs, users, keys, credits with reasons, platform stats, review queue, survey results | 2 days |
| **E. API docs + rate limits + idempotency** | Public docs page, token buckets, `Idempotency-Key` | 1–2 days |
| **F. Payments** | Razorpay packs, webhook, invoices, alerts; auto top-up | 3 days |
| **G. Domain + SSO** | Own domain; domain verification + JIT; WorkOS/Clerk SAML when a customer needs it; SCIM | 2 days + per customer |

**Demo on 3 October:** A, the landing page and Check from B, and the core of C
(members, keys, usage) can be ready, with buying credits shown in Razorpay test mode
if F fits, else as "an admin adds credits". Nothing is dropped; the rest follows in
order.

## 11. Decisions (2026-09-30)

Decided by the user:

1. **Web stack:** Next.js.
2. **Payments:** Razorpay from the start, in **test mode** (test key id and secret in
   `.env` as `FACTIFY_BILLING__RAZORPAY_KEY_ID` / `_KEY_SECRET` / `_WEBHOOK_SECRET`;
   test cards and UPI move no real money). Live keys replace them after KYC. The
   admin can still add credits by hand, logged.
3. **Pricing:** text, link, picture, PDF = 1 credit; video = 3; an answer from the
   cache = 1.
4. **Org history:** personal history stays in the browser; an org owner can opt in to
   a shared server history of org checks, stated in the privacy policy.

Still open (proposed defaults are used until decided):

5. When a member is removed: revoke their keys (default) or move them to an owner.
6. Org members keep their personal 100 free credits alongside the org pool, via the
   account switcher (default: yes).
7. A domain name for the website.

## 12. What is built (2026-09-30)

**Server** (`app/orgs/`, `app/api/orgs.py`, `app/api/admin.py`, migration 0006):
- Organisations, roles (owner, developer, member), invites by link, member limits.
- The shared pool with hold-then-settle: 50 parallel checks against 10 credits run
  exactly 10 (tests/unit/test_orgs.py). Member, key and org monthly limits; failed
  checks release their hold; a video costs 3.
- API keys: `fct_live_` with checksum, hashed, shown once; rotate with 24 h grace;
  IP allowlist; expiry; 60/min per key and 300/min per org; error codes;
  Idempotency-Key replay; `Factify-Credits-*` headers.
- Usage (JSON and CSV), the audit log, opt-in shared history.
- Razorpay test mode (orders, signed confirmation, signed webhook, invoices).
- DNS-verified domains with auto-join (JIT).
- The staff admin API.
- Google sign-in returning to the website; disabled accounts.

**Website** (`web/`, Next.js):
- Public pages: the landing page, privacy, terms and API docs.
- Sign-in and sign-up (email and Google), with the session in an httpOnly cookie
  behind a proxy.
- The dashboard: Check (text, link, file, live progress, sources), History (kept in
  the browser, plus the org's shared history when switched on), Credits, Profile.
- The organisation pages: Overview, Members, API keys, Usage, Billing, Settings
  (limits, shared history, domains, close) and the Audit log, with an account
  switcher.
- The admin panel: Overview, Organisations, People, API keys and Audit.
- Tested at 375, 768 and desktop widths; no page scrolls sideways.

**Deploy:** `web/Dockerfile`, a `web` service in `deploy/docker-compose.yml`, and Caddy
routing `/v1`, `/healthz`, `/readyz` and `/openapi.json` to the API, with everything
else going to the website.

**Not built, and why:**
- **Emails:** there is no mail service yet. Invites are links the owner copies, and
  alerts show in the dashboard.
- **Auto top-up:** needs saved cards (Razorpay recurring payments).
- **SAML SSO and SCIM:** need a WorkOS or Clerk account.
- **GitHub secret scanning:** needs GitHub's partner programme.
- **Our own domain:** none bought yet.

## 13. More admin control (proposed 2026-09-30)

**Built now:**
- The admin opens any organisation in its own view (`/app/admin/organisations/{id}`),
  not as an owner. It has tabs for Overview, Members, API keys, Usage, Billing,
  Settings and the Audit log. From there the admin can:
  - add or remove credits, with a reason;
  - set the monthly cap;
  - suspend or restore the organisation;
  - change any member's role and limit, suspend or remove them;
  - edit, rotate or revoke any key.
- The overview shows the pool, the month against the cap, a 30-day chart, dashboard
  versus API use, and members and keys ranked by spend, with each member's last
  activity and lifetime spend.

**Next, needing server work:**

1. **Organisation plans and overrides.** A plan per organisation (Free, Team, Newsroom,
   Enterprise). Per-organisation rate limits that replace the defaults of 60 and 300
   requests a minute. A custom price for a video check. Private notes for staff.
2. **Owners and transfer.** An admin can make any member owner, transfer ownership, or
   add someone to an organisation directly without an invitation.
3. **API keys across the platform.** Filter by organisation, status, creator and last
   use. See each key's usage over time and error rate. Revoke many at once. A rate
   limit per key. Mark a key "leaked", which revokes it and notifies the owner with a
   reason.
4. **People detail.**
   - Each person's organisations and roles, personal credit ledger and survey answers.
   - Sign them out everywhere (end all sessions).
   - Reset their password: set a temporary one, or send a link once email exists.
5. **Staff roles.** A super-admin (everything) and a support role (read-only, plus
   adding credits). Every staff action goes in the audit log with the staff member's
   name.
6. **Refunds and invoices.** Refund a Razorpay payment from the admin panel: take the
   credits back and record the refund. Download invoices for any organisation.
7. **Alerts for the team.** Organisations running out of credits, keys with sudden
   spikes, failed payments, and provider quotas near their limits, all in one list on
   the admin overview.
8. **See it as they do.** A read-only view of the dashboard as a given owner or member,
   to help with support.
