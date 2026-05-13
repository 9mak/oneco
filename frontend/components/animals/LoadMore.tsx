'use client';

import { useState, useTransition } from 'react';
import { AnimalCard } from './AnimalCard';
import { loadMoreAnimals } from '@/app/actions';
import type { AnimalPublic, FilterState } from '@/types/animal';

interface LoadMoreProps {
  initialOffset: number;
  totalCount: number;
  filters: FilterState;
  pageSize?: number;
}

export function LoadMore({
  initialOffset,
  totalCount,
  filters,
  pageSize = 20,
}: LoadMoreProps) {
  const [items, setItems] = useState<AnimalPublic[]>([]);
  const [offset, setOffset] = useState(initialOffset);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const handleLoadMore = () => {
    setError(null);
    startTransition(async () => {
      try {
        const result = await loadMoreAnimals({
          ...filters,
          offset,
          limit: pageSize,
        });
        setItems((prev) => [...prev, ...result.items]);
        setOffset((prev) => prev + result.items.length);
      } catch {
        setError('追加データの読み込みに失敗しました。もう一度お試しください。');
      }
    });
  };

  if (offset >= totalCount) return null;

  return (
    <>
      {items.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
          {items.map((animal) => (
            <AnimalCard key={animal.id} animal={animal} />
          ))}
        </div>
      )}

      {error && (
        <p role="alert" className="text-center text-sm text-red-600">
          {error}
        </p>
      )}

      <div className="flex justify-center">
        <button
          onClick={handleLoadMore}
          disabled={isPending}
          className="px-8 py-3 bg-[var(--color-primary-700)] text-white rounded-lg font-medium hover:bg-[var(--color-primary-800)] transition-colors focus:outline-none focus:ring-2 focus:ring-[var(--color-focus-ring)] focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed min-h-[44px] min-w-[44px]"
          aria-label="もっと見る"
        >
          {isPending ? '読み込み中...' : 'もっと見る'}
        </button>
      </div>
    </>
  );
}
