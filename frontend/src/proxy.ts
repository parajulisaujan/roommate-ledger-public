import { NextRequest, NextResponse } from "next/server";

// Server-only origin credential. Never add it to next.config env or NEXT_PUBLIC_*.
export function proxy(request: NextRequest) {
  if (process.env.DEPLOYMENT_PROXY_REQUIRED !== "true")
    return NextResponse.next();

  // A mistaken promotion must not expose this staging frontend on a public
  // Vercel Production domain, whose default protection differs from Preview.
  if (process.env.VERCEL && process.env.VERCEL_ENV !== "preview")
    return new NextResponse("Not found", {
      status: 404,
      headers: { "Cache-Control": "no-store" },
    });

  if (!request.nextUrl.pathname.startsWith("/api/")) return NextResponse.next();
  const key = process.env.DEPLOYMENT_PROXY_KEY || "";
  let target: URL;
  try {
    target = new URL(process.env.API_INTERNAL_URL || "");
    if (
      key.length < 32 ||
      target.protocol !== "https:" ||
      target.username ||
      target.password ||
      target.pathname !== "/" ||
      target.search ||
      target.hash
    )
      throw new Error("Invalid protected upstream");
  } catch {
    return new NextResponse("Staging API is not configured", {
      status: 503,
      headers: { "Cache-Control": "no-store" },
    });
  }
  target.pathname = request.nextUrl.pathname;
  target.search = request.nextUrl.search;
  const headers = new Headers(request.headers);
  // Override client-supplied credentials and do not forward proxy identity claims.
  headers.set("x-ledger-proxy-key", key);
  headers.delete("authorization");
  headers.delete("x-forwarded-for");
  headers.delete("forwarded");
  // request.headers are upstream-only; response headers must never contain the key.
  return NextResponse.rewrite(target, { request: { headers } });
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
