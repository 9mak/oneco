'use client';

import { useFavorites } from '@/lib/favorites';
import type { MouseEvent } from 'react';

interface FavoriteButtonProps {
  animalId: number;
  size?: 'sm' | 'md' | 'lg';
  /** Link 内に置く場合に親のクリック・遷移を防ぐ */
  stopPropagation?: boolean;
}

const SIZE_CLASS = {
  sm: 'w-8 h-8',
  md: 'w-10 h-10',
  lg: 'w-12 h-12',
};

const ICON_SIZE = {
  sm: 16,
  md: 20,
  lg: 24,
} as const;

export function FavoriteButton({
  animalId,
  size = 'md',
  stopPropagation = false,
}: FavoriteButtonProps) {
  const { has, toggle } = useFavorites();
  const isFav = has(animalId);

  const handleClick = (e: MouseEvent<HTMLButtonElement>) => {
    if (stopPropagation) {
      e.preventDefault();
      e.stopPropagation();
    }
    toggle(animalId);
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      aria-label={isFav ? 'お気に入りから外す' : 'お気に入りに追加'}
      aria-pressed={isFav}
      className={[
        SIZE_CLASS[size],
        'rounded-full bg-white/90 backdrop-blur-sm shadow-md',
        'flex items-center justify-center',
        'hover:scale-110 transition-transform',
        'focus:outline-none focus:ring-2 focus:ring-[var(--color-focus-ring)]',
      ].join(' ')}
    >
      <HeartIcon filled={isFav} size={ICON_SIZE[size]} />
    </button>
  );
}

/**
 * SVG ハートアイコン。Unicode ♡♥ はフォント依存 (Apple Color Emoji 等で
 * 派手な絵文字になる) で「変な感じ」になるため SVG で固定する。
 */
function HeartIcon({ filled, size }: { filled: boolean; size: number }) {
  const colorClass = filled ? 'text-red-500' : 'text-gray-400 hover:text-red-400';
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={filled ? 'currentColor' : 'none'}
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`${colorClass} transition-colors`}
      aria-hidden="true"
    >
      <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
    </svg>
  );
}
