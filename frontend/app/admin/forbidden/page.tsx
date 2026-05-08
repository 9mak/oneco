import { signOut } from '@/auth';

export const metadata = {
  title: 'アクセス拒否 | oneco',
  robots: { index: false, follow: false },
};

export default function ForbiddenPage() {
  async function signOutAction() {
    'use server';
    await signOut({ redirectTo: '/admin/signin' });
  }

  return (
    <main className="mx-auto flex min-h-[60vh] max-w-md flex-col items-center justify-center px-4 text-center">
      <h1 className="mb-4 text-xl font-bold">アクセス拒否</h1>
      <p className="mb-6 text-sm text-gray-600">
        このGitHubアカウントは管理ダッシュボードへのアクセス権限を持ちません。
      </p>
      <form action={signOutAction}>
        <button
          type="submit"
          className="rounded border border-gray-300 px-4 py-2 hover:bg-gray-50"
        >
          別アカウントでサインインする
        </button>
      </form>
    </main>
  );
}
