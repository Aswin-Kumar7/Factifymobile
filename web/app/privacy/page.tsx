import type { Metadata } from "next";
import { Prose, SiteFooter, SiteHeader } from "@/components/site";

export const metadata: Metadata = { title: "Privacy policy" };

const CONTACT = "aswin.aswin5640@gmail.com";

export default function Privacy() {
  return (
    <>
      <SiteHeader />
      <Prose>
        <h1>Privacy policy</h1>
        <p>Last updated 2 October 2026. This policy covers the Factify app, this website and the Factify API.</p>

        <h2>What we keep about you</h2>
        <ul>
          <li>
            <strong>Your account:</strong> your email address, the name you give (optional), and, if you sign in with
            Google, the name, email address and profile picture Google shares with us. We ask Google only for your
            basic profile and email (the <code>openid</code>, <code>email</code> and <code>profile</code> permissions).
          </li>
          <li>
            <strong>Your password</strong>, if you use one, only as a salted hash; we never store the password itself.
            Signed-in sessions and API keys are stored only as a hash.
          </li>
          <li>
            <strong>Your credits:</strong> when a check was made, how many credits it used and, for an organisation,
            which member or API key made it. This record does not say what was checked.
          </li>
          <li>
            <strong>Your survey answers</strong>, if you give them: who you are (for example a student or a
            journalist), where you see things to check, what you want to check, and how you heard of Factify. Every
            question can be skipped.
          </li>
          <li>
            <strong>Organisations:</strong> the organisation&apos;s name, billing email and GST number, its members and
            their roles and limits, its API keys, domains it has verified, payments, and a log of changes made to it.
          </li>
        </ul>

        <h2>What happens to what you check</h2>
        <p>
          The text, link, picture, video or PDF you send is processed to check it. The claims found in it,
          the sources consulted and the verdict are stored so that the same claim can be answered faster next time,
          but they are <strong>not linked to your account</strong>: we do not keep a record of what you checked. Your
          own list of past checks is kept on your phone, or in your browser on this website, not on our server.
        </p>
        <p>
          <strong>Pictures, videos and PDFs you upload are not stored.</strong> They are read in memory, or in temporary
          files deleted as soon as the check ends. Location data is removed from a photo before it is checked. We keep a
          fingerprint of each picture checked (a code computed from it, not the picture itself) and what was found
          about it, so the same picture is recognised if it is sent again. When a check finds an earlier copy of your
          picture online, a small copy of that earlier picture is kept in our server&apos;s memory for about an hour so
          the answer can show it, then forgotten.
        </p>
        <p>
          <strong>The one exception is an organisation&apos;s shared history.</strong> An organisation&apos;s owner can
          switch it on. While it is on, checks made for that organisation are listed for its members: the check, its
          verdict, when, and which member or key made it. It is off unless the owner turns it on, and applies only to
          checks made for the organisation, never to personal ones.
        </p>

        <h2>Payments</h2>
        <p>
          Plans and organisation credits are paid through Razorpay. Your card, UPI or bank details go to Razorpay, not
          to us; we keep the order, the amount, what it bought and Razorpay&apos;s payment reference.
        </p>

        <h2>Services that process your content</h2>
        <p>To check something, parts of it are sent to these services, only for that purpose:</p>
        <ul>
          <li>Microsoft Azure: hosts Factify and runs the language model that finds claims and reads the text in pictures.</li>
          <li>Tavily: web search for sources about a claim.</li>
          <li>
            Google: the Fact Check Tools API (published fact-checks), translation of claims to find sources in other
            languages, and, for pictures where enabled, Cloud Vision (earlier copies of a picture online).
          </li>
          <li>Supabase: hosts our database.</li>
          <li>Razorpay: payments.</li>
        </ul>
        <p>
          Pictures and videos are examined for AI generation, face swaps and, in a video&apos;s sound, machine voices by
          models that run on our own server.
        </p>

        <h2>What we don&apos;t do</h2>
        <p>
          We don&apos;t sell your data, show ads, or share your account details with anyone except the services above as
          needed to run Factify.
        </p>

        <h2>Deleting your account</h2>
        <p>
          Delete your account from Settings in the dashboard or Profile in the app: your sign-in, credits, plan,
          payments and survey answers are deleted at once. If you are the only owner of an organisation, make someone
          else an owner or close it from its settings first. You can also email{" "}
          <a href={`mailto:${CONTACT}`}>{CONTACT}</a> from the address on your account and we will do it for you.
        </p>

        <h2>Contact</h2>
        <p>
          Questions about this policy: <a href={`mailto:${CONTACT}`}>{CONTACT}</a>.
        </p>
      </Prose>
      <SiteFooter />
    </>
  );
}
