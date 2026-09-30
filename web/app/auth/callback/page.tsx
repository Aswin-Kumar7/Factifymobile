"use client";

// Where Google sign-in returns on the web. The session is in the URL's fragment
// (never sent to any server's logs); it is handed to /api/auth/session, which puts
// it in an httpOnly cookie, and the fragment is wiped from the address bar.
import { useEffect, useState } from "react";
import { authAction } from "@/lib/api";
import { safeNext } from "@/components/auth-form";
import { Seal, Spinner } from "@/components/ui";

export default function Callback() {
  const [failed, setFailed] = useState<string | null>(null);

  useEffect(() => {
    const values = new URLSearchParams(window.location.hash.slice(1));
    window.history.replaceState(null, "", window.location.pathname);
    let next = "/app/check";
    try {
      next = safeNext(sessionStorage.getItem("fct_next"));
      sessionStorage.removeItem("fct_next");
    } catch {}
    const error = values.get("error");
    if (error) {
      window.location.replace(`/signin?error=${encodeURIComponent(error)}`);
      return;
    }
    authAction("session", {
      access_token: values.get("access_token"),
      expires_at: values.get("expires_at"),
      email: values.get("email"),
    })
      .then(() => window.location.replace(next))
      .catch(() => setFailed("Sign-in didn't finish. Try again."));
  }, []);

  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-4 px-4 text-center">
      <Seal size={56} />
      {failed ? (
        <>
          <p className="text-ink2">{failed}</p>
          <a href="/signin" className="font-semibold text-acc-ink">
            Back to sign in
          </a>
        </>
      ) : (
        <p className="flex items-center gap-2 text-ink2">
          <Spinner /> Signing you in…
        </p>
      )}
    </main>
  );
}
