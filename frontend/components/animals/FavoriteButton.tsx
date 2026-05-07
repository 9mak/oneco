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
  sm: 'w-8 h-8 text-lg',
  md: 'w-10 h-10 text-2xl',
  lg: 'w-12 h-12 text-3xl',
};

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
      <span className={isFav ? 'text-red-500' : 'text-gray-400'} aria-hidden="true">
        {isFav ? '♥' : '♡'}
      </span>
    </button>
  );
}
