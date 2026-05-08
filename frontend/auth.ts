import NextAuth from 'next-auth';
import GitHub from 'next-auth/providers/github';

const ALLOWED_LOGIN = process.env.ADMIN_GITHUB_LOGIN ?? '';

export const { handlers, signIn, signOut, auth } = NextAuth({
  providers: [GitHub],
  callbacks: {
    signIn({ profile }) {
      if (!ALLOWED_LOGIN) return false;
      const login = (profile as { login?: string } | null)?.login;
      return typeof login === 'string' && login === ALLOWED_LOGIN;
    },
    jwt({ token, profile }) {
      if (profile && 'login' in profile) {
        token.login = (profile as { login?: string }).login;
      }
      return token;
    },
    session({ session, token }) {
      if (token.login) {
        (session.user as { login?: string }).login = token.login as string;
      }
      return session;
    },
  },
  pages: {
    signIn: '/admin/signin',
  },
});
