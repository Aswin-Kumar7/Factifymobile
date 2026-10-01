import type { Metadata } from "next";
import { Prose, SiteFooter, SiteHeader } from "@/components/site";

export const metadata: Metadata = { title: "Terms of service" };

export default function Terms() {
  return (
    <>
      <SiteHeader />
      <Prose>
        <h1>Terms of service</h1>
        <p>Last updated 2 October 2026.</p>

        <h2>What Factify is</h2>
        <p>
          Factify helps you judge whether something is true by finding and showing sources. Its verdicts are based on
          the sources it could find and read at the time; they are not legal, medical or financial advice. Read the
          sources before relying on an answer. When the sources don&apos;t settle a claim, Factify says Unconfirmed.
        </p>

        <h2>Your account</h2>
        <p>
          You need an account to check. Keep your password and API keys secret; you are responsible for what is done
          with them. We may suspend accounts or keys used to abuse the service, to overload it, or to break the law.
        </p>

        <h2>Credits</h2>
        <p>
          A check uses one check from your plan for text, a link, a picture or a PDF, and three for a video. A check
          that fails uses nothing. The Free plan gives 30 checks each calendar month. Paid plans are paid for a month or
          a year at a time and do not renew by themselves; when the period you paid for ends, the account goes back to
          Free. Extra usage, if you turn it on, is billed at the price shown on the pricing page. Credits an
          organisation buys are for its members and keys, are not refundable except where the law requires, and do not
          expire while the organisation is open.
        </p>

        <h2>Organisations</h2>
        <p>
          The owners of an organisation manage its members, limits, API keys and billing, and are responsible for how
          its members use Factify. An organisation must always have at least one owner.
        </p>

        <h2>The API</h2>
        <p>
          API keys are for the organisation that created them. Don&apos;t share them or put them in public code. We
          limit how many requests a key may make per minute, and may change prices with notice on this website.
        </p>

        <h2>Contact</h2>
        <p>
          <a href="mailto:aswin.aswin5640@gmail.com">aswin.aswin5640@gmail.com</a>
        </p>
      </Prose>
      <SiteFooter />
    </>
  );
}
