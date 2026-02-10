/**
 * 404 Error Page (Server Component)
 * 動物が見つからない場合のエラーページ
 * Requirements: 2.8
 */

import Link from 'next/link';

export default function NotFoundPage() {
  return (
    <main className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="text-center px-4">
        <h1 className="text-4xl font-bold text-gray-900 mb-4">
          この動物は見つかりませんでした
        </h1>

        <p className="text-lg text-gray-600 mb-8">
          お探しの動物は既に譲渡された可能性があります。
        </p>

        <Link
          href="/"
          className="inline-flex items-center justify-center px-6 py-3 text-base font-medium text-white bg-[var(--color-primary-500)] hover:bg-[var(--color-primary-700)] rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[var(--color-primary-500)] min-h-[44px] min-w-[44px]"
        >
          一覧に戻る
        </Link>
      </div>
    </main>
  );
}

/**
 * メタデータ
 */
export const metadata = {
  title: '動物が見つかりません - 404',
  description: 'お探しの動物は見つかりませんでした。',
};
