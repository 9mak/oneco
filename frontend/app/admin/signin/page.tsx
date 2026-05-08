import { signIn } from '@/auth';

export const metadata = {
  title: '管理者サインイン | oneco',
  robots: { index: false, follow: false },
};

export default function SignInPage() {
  async function signInAction() {
    'use server';
    await signIn('github', { redirectTo: '/admin' });
  }

  return (
    <main className="mx-auto flex min-h-[60vh] max-w-md flex-col items-center justify-center px-4">
      <h1 className="mb-4 text-xl font-bold">管理ダッシュボード</h1>
      <p className="mb-6 text-sm text-gray-600">
        管理者として GitHub アカウントでサインインしてください。
      </p>
      <form action={signInAction}>
        <button
          type="submit"
          className="rounded bg-gray-900 px-4 py-2 text-white hover:bg-gray-700"
        >
          GitHub でサインイン
        </button>
      </form>
    </main>
  );
}
