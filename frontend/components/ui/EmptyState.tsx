import Link from 'next/link';

interface EmptyStateProps {
  message?: string;
  /** message の下に表示する補助説明 (状況の理由 or 次のアクション提案) */
  suggestion?: string;
  showClearButton?: boolean;
}

export function EmptyState({
  message = '現在表示できる動物がいません',
  suggestion,
  showClearButton = false,
}: EmptyStateProps) {
  return (
    <div
      role="alert"
      className="flex flex-col items-center justify-center gap-5 p-10 sm:p-12 bg-gray-50 rounded-lg border-2 border-dashed border-gray-300"
    >
      <div className="w-16 h-16 rounded-full bg-gray-200 flex items-center justify-center">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="w-8 h-8 text-gray-400"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
      </div>

      <div className="flex flex-col gap-2 items-center max-w-md">
        <p className="text-lg font-medium text-[var(--color-text-primary)] text-center">
          {message}
        </p>
        {suggestion && (
          <p className="text-sm text-[var(--color-text-secondary)] text-center">
            {suggestion}
          </p>
        )}
      </div>

      {showClearButton && (
        <Link
          href="/"
          className="px-6 py-3 bg-[var(--color-primary-700)] text-white rounded-lg font-medium hover:bg-[var(--color-primary-800)] transition-colors focus:outline-none focus:ring-2 focus:ring-[var(--color-focus-ring)] focus:ring-offset-2 min-h-[44px] min-w-[44px]"
          aria-label="フィルタをクリア"
        >
          フィルタをクリア
        </Link>
      )}
    </div>
  );
}
