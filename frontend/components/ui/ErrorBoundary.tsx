/**
 * ErrorBoundary Component
 * TanStack Query のエラー状態を表示し、再試行機能を提供
 */

'use client';

interface ErrorBoundaryProps {
  /** エラーメッセージ */
  error?: Error | null;
  /** 再試行ハンドラ */
  onRetry?: () => void;
  /** カスタムエラーメッセージ */
  message?: string;
}

export function ErrorBoundary({
  error,
  onRetry,
  message = 'APIに接続できませんでした。しばらくしてから再試行してください。',
}: ErrorBoundaryProps) {
  return (
    <div
      role="alert"
      className="flex flex-col items-center justify-center gap-6 p-12 bg-red-50 rounded-lg border-2 border-red-200"
    >
      {/* エラーアイコン */}
      <div className="w-16 h-16 rounded-full bg-red-100 flex items-center justify-center">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="w-8 h-8 text-red-600"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
      </div>

      {/* エラーメッセージ */}
      <div className="text-center space-y-2">
        <h3 className="text-lg font-semibold text-red-900">
          エラーが発生しました
        </h3>
        <p className="text-sm text-red-700">
          {message}
        </p>
        {error && process.env.NODE_ENV === 'development' && (
          <details className="mt-4 text-left">
            <summary className="cursor-pointer text-xs text-red-600 hover:text-red-800">
              詳細を表示
            </summary>
            <pre className="mt-2 text-xs bg-red-100 p-4 rounded overflow-auto max-w-lg">
              {error.message}
            </pre>
          </details>
        )}
      </div>

      {/* 再試行ボタン */}
      {onRetry && (
        <button
          onClick={onRetry}
          className="px-6 py-3 bg-red-600 text-white rounded-lg font-medium hover:bg-red-700 transition-colors focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 min-h-[44px] min-w-[44px]"
          aria-label="再試行"
        >
          再試行
        </button>
      )}
    </div>
  );
}
