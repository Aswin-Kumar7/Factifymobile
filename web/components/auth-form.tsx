"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ApiFailure, authAction } from "@/lib/api";
import { ThemeButton } from "./theme";
import { Button, Field, Input, Notice, Wordmark } from "./ui";

const problems: Record<string, string> = {
  invalid_email: "That doesn't look like an email address.",
  weak_password: "Use a password of at least 8 characters.",
  email_taken: "There's already an account with this email. Sign in instead.",
  wrong_credentials: "That email and password don't match an account.",
  use_google: "This account signs in with Google. Use Continue with Google.",
  too_many_attempts: "Too many attempts. Wait a few minutes and try again.",
  google_failed: "Google sign-in didn't work. Try again, or use your email.",
  google_cancelled: "Google sign-in was cancelled.",
  google_unavailable: "Google sign-in isn't set up on this server yet. Use your email and a password.",
};

export function safeNext(next: string | null) {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/app/check";
}

export function AuthForm({ mode }: { mode: "signin" | "signup" }) {
  const router = useRouter();
  const params = useSearchParams();
  const next = safeNext(params.get("next"));
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [shown, setShown] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(problems[params.get("error") ?? ""] ?? null);
  const creating = mode === "signup";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await authAction(creating ? "register" : "login", {
        email,
        password,
        ...(creating && name.trim() ? { name: name.trim() } : {}),
      });
      router.replace(next);
      router.refresh();
    } catch (failure) {
      const code = failure instanceof ApiFailure ? (failure.code ?? failure.message) : "";
      setError(problems[code] ?? (failure as Error).message);
      setBusy(false);
    }
  }

  const nextQuery = params.get("next") ? `?next=${encodeURIComponent(next)}` : "";

  return (
    <div className="mx-auto w-full max-w-[420px]">
      <h1 className="text-[2.4rem] leading-tight font-medium tracking-tight text-ink">{creating ? "Create your account" : "Welcome back"}</h1>
      <p className="mt-2 text-[15.5px] leading-relaxed text-ink2">
        {creating ? "30 free checks every month. It takes less than a minute." : "Sign in to check forwards, links, pictures and videos."}
      </p>

      <div role="tablist" aria-label="Account" className="mt-7 inline-flex rounded-[12px] border border-line2 p-1">
        <Link
          href={`/signin${nextQuery}`}
          role="tab"
          aria-selected={!creating}
          className={`rounded-[9px] px-4 py-2 text-sm font-medium transition-colors ${!creating ? "bg-hover text-ink" : "text-ink2 hover:text-ink"}`}
        >
          Sign in
        </Link>
        <Link
          href={`/signup${nextQuery}`}
          role="tab"
          aria-selected={creating}
          className={`rounded-[9px] px-4 py-2 text-sm font-medium transition-colors ${creating ? "bg-hover text-ink" : "text-ink2 hover:text-ink"}`}
        >
          Create account
        </Link>
      </div>

      <a
        href={`/v1/auth/google/start?to=web`}
        onClick={() => {
          try {
            sessionStorage.setItem("fct_next", next);
          } catch {}
        }}
        className="mt-6 flex h-11.5 w-full items-center justify-center gap-3 rounded-[10px] border border-line2 font-medium text-ink transition-colors hover:bg-hover"
      >
        <svg width="20" height="20" viewBox="0 0 48 48" aria-hidden="true">
          <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3 0 5.8 1.1 7.9 3l5.7-5.7C34.1 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z" />
          <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 15.1 19 12 24 12c3 0 5.8 1.1 7.9 3l5.7-5.7C34.1 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
          <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z" />
          <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z" />
        </svg>
        Continue with Google
      </a>

      <div className="my-5 flex items-center gap-3.5 text-[13px] text-ink3">
        <span className="h-px flex-1 bg-line2" />
        or with email
        <span className="h-px flex-1 bg-line2" />
      </div>

      <form onSubmit={submit} className="space-y-3.5">
        {creating && (
          <Field label="Your name">
            <Input value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" placeholder="What should we call you?" />
          </Field>
        )}
        <Field label="Email">
          <Input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            placeholder="you@example.com"
          />
        </Field>
        <Field label="Password" hint={creating ? "At least 8 characters" : undefined}>
          <div className="relative">
            <Input
              type={shown ? "text" : "password"}
              required
              minLength={creating ? 8 : undefined}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={creating ? "new-password" : "current-password"}
              className="pr-16"
            />
            <button
              type="button"
              onClick={() => setShown(!shown)}
              className="absolute top-1/2 right-2 -translate-y-1/2 rounded-lg px-2 py-1 text-[13px] font-medium text-ink3 hover:bg-hover hover:text-ink"
            >
              {shown ? "Hide" : "Show"}
            </button>
          </div>
        </Field>
        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" busy={busy} className="w-full" size="lg">
          {creating ? "Create account" : "Sign in"}
        </Button>
      </form>

      <p className="mt-6 text-[13px] leading-relaxed text-ink3">
        By continuing you agree to the{" "}
        <Link href="/terms" className="text-acc-ink">
          Terms
        </Link>{" "}
        and{" "}
        <Link href="/privacy" className="text-acc-ink">
          Privacy policy
        </Link>
        . Your past checks are listed only in your browser or on your phone; what you check is stored without your name.
      </p>
    </div>
  );
}

const EXAMPLES = [
  { kind: "WhatsApp forward", claim: "Applications are open for the National Sports Scholarship 2026-27.", verdict: "False", tone: "text-false", source: "Government fact-check unit" },
  { kind: "News link", claim: "ISRO's Chandrayaan-3 landed near the Moon's south pole.", verdict: "True", tone: "text-true", source: "7 independent sources" },
  { kind: "Screenshot", claim: "Govt to pay ₹5,000 a month to every woman.", verdict: "Partly true", tone: "text-mis", source: "One state's scheme, not national" },
];

/** A few example answers, one at a time: what Factify gives back. Illustrations, labelled so. */
function Examples() {
  const [i, setI] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setI((x) => (x + 1) % EXAMPLES.length), 3200);
    return () => clearInterval(t);
  }, []);
  const ex = EXAMPLES[i];
  return (
    <div className="relative mx-auto w-full max-w-[420px]">
      <div key={i} className="fade-in rounded-[20px] border border-line2 bg-sf/90 p-6 shadow-lift backdrop-blur-md">
        <div className="text-[13px] text-ink3">Example · {ex.kind}</div>
        <p className="mt-2.5 mb-4.5 text-[17px] leading-relaxed text-ink">“{ex.claim}”</p>
        <div className="flex items-center justify-between gap-3 border-t border-line pt-4">
          <span className={`text-[1.75rem] font-medium tracking-tight ${ex.tone}`}>{ex.verdict}</span>
          <span className="text-right text-[13px] text-ink2">{ex.source}</span>
        </div>
      </div>
      <div className="mt-4 flex justify-center gap-1.5" aria-hidden="true">
        {EXAMPLES.map((_, n) => (
          <span key={n} className={`h-1.5 rounded-full transition-all duration-500 ${n === i ? "w-5.5 bg-acc-ink" : "w-1.5 bg-line2"}`} />
        ))}
      </div>
    </div>
  );
}

/** How many sites web search may cite, counted by the API (GET /v1/sources/summary). */
function useTrustedSites() {
  const [sites, setSites] = useState<number | null>(null);
  useEffect(() => {
    let live = true;
    fetch("/v1/sources/summary")
      .then((r) => (r.ok ? (r.json() as Promise<{ sites: number }>) : null))
      .then((d) => live && d && typeof d.sites === "number" && setSites(d.sites))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);
  return sites;
}

export function AuthShell({ children, mode = "signin" }: { children: React.ReactNode; mode?: "signin" | "signup" }) {
  const sites = useTrustedSites();
  return (
    <div className="relative flex min-h-dvh flex-col overflow-hidden">
      <div className="pointer-events-none absolute -top-72 -right-48 h-[900px] w-[900px] rounded-full bg-[radial-gradient(circle,var(--glow),transparent_62%)]" aria-hidden="true" />
      <header className="relative flex items-center justify-between px-5 py-5 sm:px-8">
        <Wordmark size={24} />
        <span className="flex items-center gap-3 text-sm text-ink3">
          <span className="hidden sm:inline">
            {mode === "signup" ? "Already have an account? " : "New to Factify? "}
            <Link href={mode === "signup" ? "/signin" : "/signup"} className="text-acc-ink">
              {mode === "signup" ? "Sign in" : "Create an account"}
            </Link>
          </span>
          <ThemeButton />
        </span>
      </header>
      <main className="relative mx-auto grid w-full max-w-[1360px] flex-1 gap-6 px-5 pb-8 sm:px-8 lg:grid-cols-2">
        <section className="flex items-center justify-center py-6">{children}</section>
        <aside className="relative hidden flex-col justify-between overflow-hidden rounded-[28px] border border-line2 bg-[linear-gradient(160deg,var(--acc-soft),transparent_60%)] p-12 lg:flex">
          <div
            className="pointer-events-none absolute inset-0 [mask-image:radial-gradient(ellipse_at_70%_30%,#000_10%,transparent_70%)] bg-[linear-gradient(var(--line)_1px,transparent_1px),linear-gradient(90deg,var(--line)_1px,transparent_1px)] bg-[size:56px_56px]"
            aria-hidden="true"
          />
          <div className="relative flex flex-col gap-3.5">
            <span className="font-mono text-xs tracking-[0.16em] text-acc-ink">30 FREE CHECKS A MONTH · NO CARD</span>
            <h2 className="text-[2.6rem] leading-[1.05] font-medium tracking-tight text-ink">
              Every answer comes <span className="text-ink3">with its sources.</span>
            </h2>
          </div>
          <Examples />
          <div className="relative flex gap-8 text-sm text-ink2">
            <span>
              <strong className="block text-[22px] font-medium text-ink">{sites === null ? "Vetted" : new Intl.NumberFormat("en-IN").format(sites)}</strong>trusted sites
            </span>
            <span>
              <strong className="block text-[22px] font-medium text-ink">12</strong>languages
            </span>
            <span>
              <strong className="block text-[22px] font-medium text-ink">0</strong>guesses
            </span>
          </div>
        </aside>
      </main>
    </div>
  );
}
