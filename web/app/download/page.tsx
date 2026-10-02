import type { Metadata } from "next";
import { DownloadPanel } from "@/components/download";
import { SiteFooter, SiteHeader } from "@/components/site";

export const metadata: Metadata = { title: "Get the Android app" };

export default function Download() {
  return (
    <>
      <SiteHeader />
      <main className="relative overflow-hidden">
        <div className="pointer-events-none absolute -top-60 left-1/2 h-[700px] w-[900px] -translate-x-1/2 bg-[radial-gradient(closest-side,var(--glow),transparent)]" aria-hidden="true" />
        <div className="relative mx-auto flex max-w-[520px] flex-col gap-6 px-5 py-14 sm:py-20">
          <div>
            <span className="eyebrow">Android app</span>
            <h1 className="mt-3 text-[2.2rem] leading-[1.08] font-medium tracking-tight text-ink">Check forwards right from WhatsApp.</h1>
            <p className="mt-3 text-[16px] leading-relaxed text-ink2">Copy a forward, then tap the floating Factify button: the answer opens over your chat. Pictures, videos and PDFs can be shared straight from WhatsApp.</p>
          </div>
          <DownloadPanel />
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
