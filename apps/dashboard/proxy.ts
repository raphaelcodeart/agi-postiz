import { NextRequest, NextResponse } from "next/server";
import { verifyPortalSessionToken, verifySessionToken } from "@/lib/auth/session";
import { PORTAL_SESSION_COOKIE_NAME, SESSION_COOKIE_NAME } from "@/lib/env";

/**
 * Route guard for the two audiences this app serves.
 *
 * /portal/* is the end-user portal and has its own session cookie, its own login
 * page and its own token audience; everything else is the administrative
 * dashboard. They are checked separately and never fall through to one another:
 * an administrator visiting /portal must sign in as a user, and a user visiting
 * the dashboard is sent to their own login rather than to the admin one.
 */
const ADMIN_PUBLIC_PATHS = ["/login"];
const PORTAL_ROOT = "/portal";
// connect-done is the provider's redirect target at the end of the hosted OAuth
// flow. It must be public: the popup is a fresh browsing context that may not
// carry the session cookie back, and bouncing the user to a login screen at the
// very end of a successful authorisation would throw away the connection.
// It renders nothing sensitive - it posts a message to its opener and closes.
const PORTAL_PUBLIC_PATHS = ["/portal/login", "/portal/register", "/portal/connect-done"];

export async function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (pathname === PORTAL_ROOT || pathname.startsWith(`${PORTAL_ROOT}/`)) {
    return portalGuard(request, pathname);
  }

  return adminGuard(request, pathname);
}

async function portalGuard(request: NextRequest, pathname: string) {
  const isPublic = PORTAL_PUBLIC_PATHS.some((path) => pathname.startsWith(path));

  const token = request.cookies.get(PORTAL_SESSION_COOKIE_NAME)?.value;
  const session = token ? await verifyPortalSessionToken(token) : null;

  if (!session && !isPublic) {
    const loginUrl = new URL("/portal/login", request.url);
    loginUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(loginUrl);
  }

  if (session && isPublic) {
    return NextResponse.redirect(new URL("/portal", request.url));
  }

  return NextResponse.next();
}

async function adminGuard(request: NextRequest, pathname: string) {
  const isPublic = ADMIN_PUBLIC_PATHS.some((path) => pathname.startsWith(path));

  const token = request.cookies.get(SESSION_COOKIE_NAME)?.value;
  const session = token ? await verifySessionToken(token) : null;

  if (!session && !isPublic) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(loginUrl);
  }

  if (session && isPublic) {
    return NextResponse.redirect(new URL("/", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};
