'use client';

import { useEffect } from 'react';
import Link from 'next/link';

export default function ErrorBoundary({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error('Page error:', error);
  }, [error]);

  return (
    <main className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="text-center px-4 max-w-md">
        <h1 className="text-3xl font-bold text-gray-900 mb-4">
          エラーが発生しました
        </h1>
        <p className="text-base text-gray-600 mb-6">
          ページの読み込み中に問題が発生しました。
          時間をおいて再度お試しください。
        </p>
        {error.digest && (
          <p className="text-xs text-gray-600 mb-6 font-mono">
            error id: {error.digest}
          </p>
        )}
        <div className="flex gap-3 justify-center flex-wrap">
          <button
            type="button"
            onClick={reset}
            className="inline-flex items-center justify-center px-6 py-3 text-base font-medium text-white bg-[var(--color-primary-700)] hover:bg-[var(--color-primary-800)] rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[var(--color-primary-500)] min-h-[44px]"
          >
            再試行
          </button>
          <Link
            href="/"
            className="inline-flex items-center justify-center px-6 py-3 text-base font-medium text-gray-700 bg-white border border-gray-300 hover:bg-gray-50 rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-300 min-h-[44px]"
          >
            一覧に戻る
          </Link>
        </div>
      </div>
    </main>
  );
}
