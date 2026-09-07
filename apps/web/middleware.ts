import { NextRequest, NextResponse } from "next/server";

/**
 * UX-only route gate (§35). Next.js middleware runs at the edge, before
 * any page code — it can see whether the session cookie is PRESENT, but
 * it cannot (and does not try to) validate it: that requires a DB
 * lookup, which only the backend does (app/api/deps_auth.py). A visitor
 * with an expired or forged cookie value sails right past this
 * middleware and hits the actual page; the backend then rejects their
 * API calls the same way it would anyone else's, exactly as if this
 * file didn't exist. Delete this file and the app is equally secure,
 * just less pleasant to use.
 */

const PROTECTED_PREFIXES = ["/account"];

export function middleware(request: NextRequest) {
  const isProtected = PROTECTED_PREFIXES.some((prefix) => request.nextUrl.pathname.startsWith(prefix));
  if (!isProtected) return NextResponse.next();

  const hasSessionCookie = request.cookies.has("c123_session");
  if (!hasSessionCookie) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("next", request.nextUrl.pathname);
    return NextResponse.redirect(loginUrl);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/account/:path*"],
};
