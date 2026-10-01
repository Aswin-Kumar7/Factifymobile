// Sign-in, sign-up, sign-out and the Google callback's hand-over.
//
// The API's session token is put in an httpOnly cookie here and never given to
// page scripts: login/register answer only with who signed in.
import { cookies } from "next/headers";
import { NextRequest } from "next/server";
import { apiBase, cookieOptions, SESSION_COOKIE } from "@/lib/server";

export const dynamic = "force-dynamic";

type Session = { access_token: string; expires_at: string; email: string; name?: string | null };

async function adopt(session: Session) {
  (await cookies()).set(SESSION_COOKIE, session.access_token, cookieOptions(new Date(session.expires_at)));
  return Response.json({ email: session.email, name: session.name ?? null });
}

export async function POST(request: NextRequest, context: { params: Promise<{ action: string }> }) {
  const { action } = await context.params;
  const jar = await cookies();

  if (action === "logout") {
    const token = jar.get(SESSION_COOKIE)?.value;
    jar.delete(SESSION_COOKIE);
    if (token) {
      await fetch(`${apiBase()}/v1/auth/logout`, {
        method: "POST",
        headers: { authorization: `Bearer ${token}` },
      }).catch(() => undefined);
    }
    return new Response(null, { status: 204 });
  }

  const body = await request.json().catch(() => ({}));

  if (action === "session") {
    // The Google callback page hands over the token it found in the URL fragment.
    if (typeof body.access_token !== "string" || !body.access_token.startsWith("fs_")) {
      return Response.json({ detail: "bad session" }, { status: 400 });
    }
    return adopt(body as Session);
  }

  if (action === "handoff") {
    // The app's one-time payment link: traded once for a short session.
    let upstream: Response;
    try {
      upstream = await fetch(`${apiBase()}/v1/billing/handoff/exchange`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ token: String(body.token ?? "") }),
      });
    } catch {
      return Response.json({ detail: "The Factify service can't be reached right now." }, { status: 502 });
    }
    const answer = await upstream.json().catch(() => ({}));
    if (!upstream.ok) return Response.json(answer, { status: upstream.status });
    jar.set(SESSION_COOKIE, answer.access_token, cookieOptions(new Date(answer.expires_at)));
    return Response.json({ email: answer.email, handoff_id: answer.handoff_id, org_id: answer.org_id });
  }

  if (action !== "login" && action !== "register") {
    return Response.json({ detail: "not found" }, { status: 404 });
  }
  let upstream: Response;
  try {
    upstream = await fetch(`${apiBase()}/v1/auth/${action}`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-forwarded-for": request.headers.get("x-forwarded-for") ?? "",
      },
      body: JSON.stringify(body),
    });
  } catch {
    return Response.json({ detail: "The Factify service can't be reached right now." }, { status: 502 });
  }
  const answer = await upstream.json().catch(() => ({}));
  if (!upstream.ok) return Response.json(answer, { status: upstream.status });
  return adopt(answer as Session);
}
