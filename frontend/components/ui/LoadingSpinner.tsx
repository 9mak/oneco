/**
 * LoadingSpinner Component
 * データ読み込み中に表示するアクセシブルなスピナー
 * ARIA属性でスクリーンリーダー対応
 */

'use client';

interface LoadingSpinnerProps {
  /** スピナーのサイズ (デフォルト: "md") */
  size?: 'sm' | 'md' | 'lg';
  /** 読み込み中のテキスト (デフォルト: "読み込み中...") */
  label?: string;
}

export function LoadingSpinner({ size = 'md', label = '読み込み中...' }: LoadingSpinnerProps) {
  // サイズに応じたスタイル
  const sizeStyles = {
    sm: 'w-6 h-6 border-2',
    md: 'w-12 h-12 border-3',
    lg: 'w-16 h-16 border-4',
  };

  const sizeStyle = sizeStyles[size];

  return (
    <div
      role="status"
      aria-label={label}
      className="flex flex-col items-center justify-center gap-4 p-8"
    >
      {/* スピナーアニメーション */}
      <div
        className={`${sizeStyle} border-[var(--color-primary-500)] border-t-transparent rounded-full animate-spin`}
        aria-hidden="true"
      />

      {/* 読み込み中のテキスト */}
      <p className="text-sm text-[var(--color-text-secondary)]">
        {label}
      </p>
    </div>
  );
}
