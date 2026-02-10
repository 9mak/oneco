/**
 * ExternalLink Component
 * 「元のページを見る」ボタン - 自治体の元ページを新しいタブで開く
 * Requirements: 2.6, 4.5, 5.5
 */

'use client';

interface ExternalLinkProps {
  /** 元のページURL */
  sourceUrl: string;
  /** ボタンラベル (デフォルト: "元のページを見る") */
  label?: string;
}

export function ExternalLink({ sourceUrl, label = '元のページを見る' }: ExternalLinkProps) {
  return (
    <a
      href={sourceUrl}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center justify-center px-6 py-3 text-base font-medium text-[var(--color-primary-500)] bg-white border-2 border-[var(--color-primary-500)] hover:bg-[var(--color-primary-50)] rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[var(--color-primary-500)] min-h-[44px] min-w-[44px]"
      aria-label={`${label}（新しいタブで開きます）`}
    >
      <svg
        className="w-5 h-5 mr-2"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
        />
      </svg>
      {label}
    </a>
  );
}
