// The browser's way to the API: /api/f/v1/... goes to the API's /v1/..., with the
// session from the httpOnly cookie added. Bodies and answers stream through
// unchanged, so uploads and live progress work as they do in the app.
import { cookies } from "next/headers";
import { NextRequest } from "next/server";
import { apiBase, SESSION_COOKIE } from "@/lib/server";

export const dynamic = "force-dynamic";

const PASS_REQUEST = ["content-type", "accept", "x-factify-account", "idempotency-key"];
const PASS_RESPONSE = [
  "content-type",
  "content-disposition",
  "retry-after",
  "factify-credits-used",
  "factify-credits-remaining",
  "cache-control",
  "x-ratelimit-limit",
  "x-ratelimit-remaining",
  "x-ratelimit-reset",
  "idempotent-replayed",
];

async function forward(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const target = `${apiBase()}/${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`;
  const headers = new Headers();
  for (const name of PASS_REQUEST) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  if (token) headers.set("authorization", `Bearer ${token}`);
  const forwardedFor = request.headers.get("x-forwarded-for");
  if (forwardedFor) headers.set("x-forwarded-for", forwardedFor);

  const hasBody = !["GET", "HEAD"].includes(request.method);
  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers,
      body: hasBody ? request.body : undefined,
      // @ts-expect-error - Node's fetch needs this to stream a request body.
      duplex: hasBody ? "half" : undefined,
      redirect: "manual",
      cache: "no-store",
    });
  } catch {
    return Response.json({ detail: "The Factify service can't be reached right now." }, { status: 502 });
  }
  const out = new Headers();
  for (const name of PASS_RESPONSE) {
    const value = upstream.headers.get(name);
    if (value) out.set(name, value);
  }
  return new Response(upstream.body, { status: upstream.status, headers: out });
}

export { forward as GET, forward as POST, forward as PUT, forward as PATCH, forward as DELETE };
