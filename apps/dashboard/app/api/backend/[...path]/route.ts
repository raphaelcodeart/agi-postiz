import { NextRequest, NextResponse } from "next/server";
import { getBackendInternalUrl, SESSION_COOKIE_NAME } from "@/lib/env";

/**
 * Same-origin BFF proxy to the FastAPI backend. The admin JWT lives only in an
 * httpOnly cookie on this server; it is attached here as a Bearer token and is
 * never exposed to client-side JavaScript. This also sidesteps CORS entirely
 * since the browser only ever talks to this Next.js origin.
 */
const HOP_BY_HOP_REQUEST_HEADERS = new Set(["host", "connection", "cookie", "content-length"]);
const FORWARDED_RESPONSE_HEADERS = ["content-type", "content-disposition", "cache-control", "location"];

async function proxy(request: NextRequest, path: string[]) {
  // Next.js catch-all route params never include a trailing slash, even though
  // FastAPI's collection routes (e.g. POST /users/) require one and 307-redirect
  // otherwise. Re-derive it from the raw incoming pathname so it round-trips.
  const joinedPath = path.join("/");
  const trailingSlash = request.nextUrl.pathname.endsWith("/") && !joinedPath.endsWith("/") ? "/" : "";
  const backendUrl = new URL(`${getBackendInternalUrl()}/api/v1/${joinedPath}${trailingSlash}`);
  backendUrl.search = request.nextUrl.search;

  const headers = new Headers();
  request.headers.forEach((value, key) => {
    if (!HOP_BY_HOP_REQUEST_HEADERS.has(key.toLowerCase())) {
      headers.set(key, value);
    }
  });

  const token = request.cookies.get(SESSION_COOKIE_NAME)?.value;
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const hasBody = !["GET", "HEAD"].includes(request.method);

  let backendResponse: Response;
  try {
    backendResponse = await fetch(backendUrl, {
      method: request.method,
      headers,
      body: hasBody ? request.body : undefined,
      // @ts-expect-error - duplex is required by undici when streaming a request body
      duplex: hasBody ? "half" : undefined,
      cache: "no-store",
      redirect: "manual",
    });
  } catch {
    return NextResponse.json({ detail: "Backend service is unreachable" }, { status: 502 });
  }

  const responseHeaders = new Headers();
  for (const name of FORWARDED_RESPONSE_HEADERS) {
    const value = backendResponse.headers.get(name);
    if (value) responseHeaders.set(name, value);
  }

  return new NextResponse(backendResponse.body, {
    status: backendResponse.status,
    headers: responseHeaders,
  });
}

type RouteContext = { params: Promise<{ path: string[] }> };

export async function GET(request: NextRequest, context: RouteContext) {
  return proxy(request, (await context.params).path);
}
export async function POST(request: NextRequest, context: RouteContext) {
  return proxy(request, (await context.params).path);
}
export async function PUT(request: NextRequest, context: RouteContext) {
  return proxy(request, (await context.params).path);
}
export async function PATCH(request: NextRequest, context: RouteContext) {
  return proxy(request, (await context.params).path);
}
export async function DELETE(request: NextRequest, context: RouteContext) {
  return proxy(request, (await context.params).path);
}
