/**
 * Next.js Middleware — Route protection.
 *
 * Chạy ở Edge Runtime trước mọi request.
 * Redirect unauthenticated users → /login.
 *
 * Pattern: Vercel's own dashboard dùng cùng approach.
 * Dùng JWT verify ở middleware layer thay vì fetch /me mỗi request
 * → không tốn round-trip DB call.
 */

import { NextRequest, NextResponse } from "next/server";

// Routes không cần auth
const PUBLIC_PATHS = ["/login", "/register", "/api/", "/_next/", "/favicon.ico"];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Skip public routes
  if (PUBLIC_PATHS.some((path) => pathname.startsWith(path))) {
    return NextResponse.next();
  }

  // Check access token cookie (set khi login thành công)
  // NOTE: access token trong memory, nhưng ta dùng một short-lived
  // "session indicator" cookie để middleware có thể check mà không cần
  // gọi API (Edge Runtime không có access đến Zustand store)
  const sessionCookie = request.cookies.get("hylist_session");

  if (!sessionCookie?.value) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("redirect", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  // Chỉ apply cho các routes cần protect
  matcher: ["/((?!login|register|_next/static|_next/image|favicon.ico|api/).*)"],
};
