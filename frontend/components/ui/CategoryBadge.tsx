/**
 * CategoryBadge Component
 * カテゴリ（譲渡対象/迷子）を視覚的に表示するバッジコンポーネント
 * WCAG 2.1 AA準拠のカラーとセマンティックなHTMLを使用
 */

'use client';

interface CategoryBadgeProps {
  /** カテゴリ ("adoption": 譲渡対象, "lost": 迷子, "sheltered": 収容中) */
  category: 'adoption' | 'lost' | 'sheltered';
  /** バッジサイズ (デフォルト: "md") */
  size?: 'sm' | 'md' | 'lg';
}

export function CategoryBadge({ category, size = 'md' }: CategoryBadgeProps) {
  // カテゴリに応じたラベルとスタイル
  const categoryConfig = {
    adoption: {
      label: '譲渡対象',
      bgColor: 'bg-[var(--color-category-adoption)]',
      textColor: 'text-white',
    },
    lost: {
      label: '迷子',
      bgColor: 'bg-[var(--color-category-lost)]',
      textColor: 'text-black',
    },
    sheltered: {
      label: '収容中',
      bgColor: 'bg-[var(--color-category-lost)]',
      textColor: 'text-black',
    },
  };

  // サイズに応じたスタイル
  const sizeStyles = {
    sm: 'px-2 py-0.5 text-xs',
    md: 'px-3 py-1 text-sm',
    lg: 'px-4 py-1.5 text-base',
  };

  const config = categoryConfig[category];
  const sizeStyle = sizeStyles[size];

  return (
    <span
      role="status"
      className={`inline-flex items-center justify-center rounded-full font-medium ${config.bgColor} ${config.textColor} ${sizeStyle}`}
      aria-label={`カテゴリ: ${config.label}`}
    >
      {config.label}
    </span>
  );
}
