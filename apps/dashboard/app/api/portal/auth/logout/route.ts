import { NextResponse } from "next/server";
import { PORTAL_SESSION_COOKIE_NAME } from "@/lib/env";

/** Clears the portal session cookie. Leaves any admin session untouched. */
export async function POST() {
  const response = NextResponse.json({ ok: true });
  response.cookies.set(PORTAL_SESSION_COOKIE_NAME, "", {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 0,
  });
  return response;
}
