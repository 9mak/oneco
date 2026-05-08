import { auth } from '@/auth';
import { NextResponse } from 'next/server';

export default auth((req) => {
  const { pathname } = req.nextUrl;
  const isAdmin = pathname.startsWith('/admin');
  const isSignIn = pathname.startsWith('/admin/signin');
  if (!isAdmin || isSignIn) return NextResponse.next();

  if (!req.auth) {
    const signInUrl = new URL('/admin/signin', req.url);
    signInUrl.searchParams.set('callbackUrl', pathname);
    return NextResponse.redirect(signInUrl);
  }

  const allowed = process.env.ADMIN_GITHUB_LOGIN ?? '';
  const login = (req.auth.user as { login?: string } | undefined)?.login;
  if (!allowed || login !== allowed) {
    return NextResponse.redirect(new URL('/admin/forbidden', req.url));
  }

  return NextResponse.next();
});

export const config = {
  matcher: ['/admin/:path*'],
};
