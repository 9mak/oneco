/**
 * EmptyState Component
 * データが0件の場合に表示する空状態コンポーネント
 * セマンティックなHTMLとアクセシブルなメッセージ
 */

'use client';

interface EmptyStateProps {
  /** 表示するメッセージ (デフォルト: "現在表示できる動物がいません") */
  message?: string;
  /** フィルタクリアボタンを表示するか (デフォルト: false) */
  showClearButton?: boolean;
  /** フィルタクリアボタンのクリックハンドラ */
  onClearFilters?: () => void;
}

export function EmptyState({
  message = '現在表示できる動物がいません',
  showClearButton = false,
  onClearFilters,
}: EmptyStateProps) {
  return (
    <div
      role="alert"
      className="flex flex-col items-center justify-center gap-6 p-12 bg-gray-50 rounded-lg border-2 border-dashed border-gray-300"
    >
      {/* アイコン */}
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

      {/* メッセージ */}
      <p className="text-lg font-medium text-[var(--color-text-primary)] text-center">
        {message}
      </p>

      {/* フィルタクリアボタン */}
      {showClearButton && onClearFilters && (
        <button
          onClick={onClearFilters}
          className="px-6 py-3 bg-[var(--color-primary-500)] text-white rounded-lg font-medium hover:bg-[var(--color-primary-700)] transition-colors focus:outline-none focus:ring-2 focus:ring-[var(--color-focus-ring)] focus:ring-offset-2 min-h-[44px] min-w-[44px]"
          aria-label="フィルタをクリア"
        >
          フィルタをクリア
        </button>
      )}
    </div>
  );
}
