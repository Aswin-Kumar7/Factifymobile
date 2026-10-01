"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { ApiFailure, authAction } from "@/lib/api";
import { Button, Field, Input, Notice, Seal } from "./ui";

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

  const other = creating ? `/signin` : `/signup`;
  const nextQuery = params.get("next") ? `?next=${encodeURIComponent(next)}` : "";

  return (
    <div className="mx-auto w-full max-w-md">
      <Link href="/" className="inline-block" aria-label="Factify home">
        <Seal size={52} />
      </Link>
      <h1 className="mt-6 font-serif text-4xl font-medium tracking-tight text-ink">
        {creating ? "Create your account" : "Welcome back"}
      </h1>
      <p className="mt-2 text-[15px] text-ink2">
        {creating ? "Start with 100 free checks. It takes a minute." : "Sign in with your email and password, or with Google."}
      </p>

      <a
        href={`/v1/auth/google/start?to=web`}
        onClick={() => {
          try {
            sessionStorage.setItem("fct_next", next);
          } catch {}
        }}
        className="mt-7 flex h-12 w-full items-center justify-center gap-3 rounded-xl border border-line bg-sf font-semibold text-ink hover:bg-sf2"
      >
        <svg width="20" height="20" viewBox="0 0 48 48" aria-hidden="true">
          <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3 0 5.8 1.1 7.9 3l5.7-5.7C34.1 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z" />
          <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 15.1 19 12 24 12c3 0 5.8 1.1 7.9 3l5.7-5.7C34.1 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
          <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z" />
          <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z" />
        </svg>
        Continue with Google
      </a>

      <div className="my-5 flex items-center gap-3 text-xs text-ink3">
        <span className="h-px flex-1 bg-line" />
        or
        <span className="h-px flex-1 bg-line" />
      </div>

      <form onSubmit={submit} className="space-y-3.5">
        {creating && (
          <Field label="Your name (optional)">
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
              className="absolute top-1/2 right-2 -translate-y-1/2 rounded-lg px-2 py-1 text-sm font-semibold text-ink3 hover:text-ink"
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

      <p className="mt-5 text-center text-[15px] text-ink2">
        {creating ? "Have an account? " : "New to Factify? "}
        <Link href={`${other}${nextQuery}`} className="font-semibold text-acc-ink">
          {creating ? "Sign in" : "Create one"}
        </Link>
      </p>
      <p className="mt-8 text-center text-xs text-ink3">
        By continuing you agree to the <Link href="/terms" className="underline">terms</Link> and{" "}
        <Link href="/privacy" className="underline">privacy policy</Link>. We never keep a record of what you check.
      </p>
    </div>
  );
}

export function AuthShell({ children }: { children: React.ReactNode }) {
  return (
    <main className="grid min-h-dvh lg:grid-cols-[1fr_1fr]">
      <div className="flex items-center px-4 py-10 sm:px-8">{children}</div>
      <aside className="hidden flex-col justify-between bg-acc p-12 text-on-acc lg:flex">
        <div className="font-serif text-2xl font-semibold">Factify</div>
        <blockquote className="max-w-md">
          <p className="font-serif text-4xl leading-tight">
            &ldquo;Every answer comes with its sources. When they don&apos;t settle it, Factify says so.&rdquo;
          </p>
        </blockquote>
        <p className="text-sm opacity-80">Text, links, pictures, videos and PDFs, in 12 languages.</p>
      </aside>
    </main>
  );
}
