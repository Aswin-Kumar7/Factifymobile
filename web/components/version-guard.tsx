"use client";

// Keeps an open tab in step with deploys.
//
// Every deploy rebuilds the site, and the new build's script files have new names;
// the old ones are gone. A tab opened before the deploy still asks for the old
// names, gets 404, and shows "page not found" until it is reloaded - which looked
// like the site going down when left idle. So: when the tab comes back into view,
// or a script fails to load, ask which build is running and reload if it changed.

import { useEffect } from "react";

export function VersionGuard({ build }: { build: string }) {
  useEffect(() => {
    if (!build || build === "dev") return;
    let reloading = false;

    async function check() {
      if (reloading) return;
      try {
        const r = await fetch("/api/version", { cache: "no-store" });
        const { build: live } = await r.json();
        if (live && live !== build) {
          // Once per new build: never a reload loop if the two ever disagree.
          const seen = sessionStorage.getItem("fct_reloaded_for");
          if (seen === live) return;
          sessionStorage.setItem("fct_reloaded_for", live);
          reloading = true;
          window.location.reload();
        }
      } catch {
        // Offline or mid-deploy: try again next time.
      }
    }

    const onVisible = () => document.visibilityState === "visible" && check();
    // A script or style of this build that no longer exists on the server.
    const onError = (e: Event) => {
      const target = e.target as HTMLElement | null;
      const src = (target as HTMLScriptElement)?.src || (target as HTMLLinkElement)?.href || "";
      if (src.includes("/_next/")) check();
    };
    const onRejection = (e: PromiseRejectionEvent) => {
      const text = String(e.reason?.name ?? "") + String(e.reason?.message ?? "");
      if (/ChunkLoadError|Loading chunk|Failed to fetch dynamically imported module/i.test(text)) check();
    };

    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("error", onError, true);
    window.addEventListener("unhandledrejection", onRejection);
    const timer = window.setInterval(check, 10 * 60 * 1000);
    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("error", onError, true);
      window.removeEventListener("unhandledrejection", onRejection);
      window.clearInterval(timer);
    };
  }, [build]);
  return null;
}
