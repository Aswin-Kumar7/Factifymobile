// Server-side only: where the API is, and the session cookie.
//
// The session token lives in an httpOnly cookie that page scripts can't read. The
// browser talks to /api/f/..., and the proxy there adds the token on the way to
// the API.

export const SESSION_COOKIE = "fct_session";

/** The API as this Next.js server reaches it (inside Docker: the app container). */
export function apiBase(): string {
  return (process.env.FACTIFY_API_INTERNAL || "http://localhost:8000").replace(/\/$/, "");
}

export const cookieOptions = (expires?: Date) => ({
  httpOnly: true,
  secure: process.env.NODE_ENV === "production",
  sameSite: "lax" as const,
  path: "/",
  expires,
});
