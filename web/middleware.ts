// The dashboard needs a session; without one it goes to sign-in and comes back.
import { NextRequest, NextResponse } from "next/server";

export function middleware(request: NextRequest) {
  if (!request.cookies.get("fct_session")) {
    const url = request.nextUrl.clone();
    url.pathname = "/signin";
    url.search = `?next=${encodeURIComponent(request.nextUrl.pathname + request.nextUrl.search)}`;
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = { matcher: ["/app/:path*"] };
