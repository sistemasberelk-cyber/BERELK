import { NextResponse } from 'next/server';

export function middleware(request) {
  const { pathname } = request.nextUrl;
  const requestHeaders = new Headers(request.headers);

  // 1. Resolve subdomain from Host header
  const hostname = request.headers.get('host') || '';
  const baseDomain = process.env.NEXT_PUBLIC_BASE_DOMAIN || 'vibecloud-frontend.onrender.com';
  
  let subdomain = '';
  if (hostname && hostname.includes('.') && !hostname.startsWith('localhost') && !hostname.startsWith('127.0.0.1')) {
    if (hostname.endsWith(baseDomain)) {
      subdomain = hostname.replace('.' + baseDomain, '');
    } else {
      subdomain = hostname.split('.')[0];
    }
  }

  if (subdomain) {
    requestHeaders.set('x-tenant-subdomain', subdomain.toLowerCase());
  }

  // 2. Redirect to onboarding for /admin routes, not the public storefront
  if (pathname.startsWith('/admin')) {
    const isOnboardedCookie = request.cookies.get('is_onboarded');
    if (isOnboardedCookie && isOnboardedCookie.value === 'false') {
      return NextResponse.redirect(new URL('/onboarding', request.url), {
        headers: requestHeaders,
      });
    }
  }

  return NextResponse.next({
    request: {
      headers: requestHeaders,
    },
  });
}

export const config = {
  matcher: [
    '/((?!api|_next/static|_next/image|favicon.ico|login|onboarding).*)',
  ],
};
