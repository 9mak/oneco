/**
 * AnimalListClient Component
 * 動物一覧表示、フィルタリング、ページネーション、TanStack Queryによるキャッシング管理
 */

'use client';

import { useInfiniteQuery } from '@tanstack/react-query';
import { useSearchParams, useRouter } from 'next/navigation';
import { AnimalPublic, PaginatedResponse, FilterState } from '@/types/animal';
import { AnimalCard } from './AnimalCard';
import { FilterPanel } from './FilterPanel';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorBoundary } from '@/components/ui/ErrorBoundary';

interface AnimalListClientProps {
  initialAnimals: AnimalPublic[];
  initialTotalCount: number;
}

export function AnimalListClient({ initialAnimals, initialTotalCount }: AnimalListClientProps) {
  const router = useRouter();
  const searchParams = useSearchParams();

  // URLクエリパラメータからフィルタ状態を取得
  const filters: FilterState = {
    category: (searchParams.get('category') as 'adoption' | 'lost' | 'sheltered') || undefined,
    species: (searchParams.get('species') as '犬' | '猫') || undefined,
    sex: (searchParams.get('sex') as '男の子' | '女の子' | '不明') || undefined,
    location: searchParams.get('location') || undefined,
  };

  // API URLを構築
  const buildApiUrl = (offset: number) => {
    const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';
    const params = new URLSearchParams();
    params.set('limit', '20');
    params.set('offset', offset.toString());
    if (filters.category) params.set('category', filters.category);
    if (filters.species) params.set('species', filters.species);
    if (filters.sex) params.set('sex', filters.sex);
    if (filters.location) params.set('location', filters.location);

    return `${baseUrl}/animals?${params.toString()}`;
  };

  // TanStack Query Infinite Query
  const {
    data,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    isLoading,
    isError,
    error,
    refetch,
  } = useInfiniteQuery({
    queryKey: ['animals', filters],
    queryFn: async ({ pageParam = 0 }) => {
      const response = await fetch(buildApiUrl(pageParam));
      if (!response.ok) {
        throw new Error('動物データの取得に失敗しました');
      }
      return response.json() as Promise<PaginatedResponse<AnimalPublic>>;
    },
    getNextPageParam: (lastPage) => {
      return lastPage.meta.has_next
        ? lastPage.meta.offset + lastPage.meta.limit
        : undefined;
    },
    initialPageParam: 0,
    // 初期データを使用（Server Componentから渡される）
    placeholderData: initialAnimals.length > 0
      ? {
          pages: [
            {
              items: initialAnimals,
              meta: {
                total_count: initialTotalCount,
                limit: 20,
                offset: 0,
                current_page: 1,
                total_pages: Math.ceil(initialTotalCount / 20),
                has_next: initialTotalCount > 20,
              },
            },
          ],
          pageParams: [0],
        }
      : undefined,
  });

  // フィルタ変更ハンドラ
  const handleFilterChange = (key: keyof FilterState, value: string | undefined) => {
    const newParams = new URLSearchParams(searchParams);
    if (value) {
      newParams.set(key, value);
    } else {
      newParams.delete(key);
    }
    router.push(`?${newParams.toString()}`);
  };

  // フィルタクリアハンドラ
  const handleClearFilters = () => {
    router.push('/');
  };

  // ローディング状態
  if (isLoading) {
    return <LoadingSpinner />;
  }

  // エラー状態
  if (isError) {
    return <ErrorBoundary error={error as Error} onRetry={() => refetch()} />;
  }

  // 動物データを平坦化
  const animals = data?.pages.flatMap((page) => page.items) || [];
  const totalCount = data?.pages[0]?.meta.total_count || 0;

  return (
    <div className="container mx-auto px-4 py-8 space-y-8">
      {/* フィルタパネル */}
      <FilterPanel
        filters={filters}
        onFilterChange={handleFilterChange}
        onClearFilters={handleClearFilters}
        resultCount={totalCount}
      />

      {/* 空状態 */}
      {animals.length === 0 && (
        <EmptyState
          message="現在表示できる動物がいません"
          showClearButton={Object.values(filters).some((v) => v !== undefined)}
          onClearFilters={handleClearFilters}
        />
      )}

      {/* 動物カードグリッド */}
      {animals.length > 0 && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
            {animals.map((animal) => (
              <AnimalCard key={animal.id} animal={animal} />
            ))}
          </div>

          {/* もっと見るボタン */}
          {hasNextPage && (
            <div className="flex justify-center">
              <button
                onClick={() => fetchNextPage()}
                disabled={isFetchingNextPage}
                className="px-8 py-3 bg-[var(--color-primary-500)] text-white rounded-lg font-medium hover:bg-[var(--color-primary-700)] transition-colors focus:outline-none focus:ring-2 focus:ring-[var(--color-focus-ring)] focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed min-h-[44px] min-w-[44px]"
                aria-label="もっと見る"
              >
                {isFetchingNextPage ? '読み込み中...' : 'もっと見る'}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
