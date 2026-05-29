import { AnimalCard } from './AnimalCard';
import { LoadMore } from './LoadMore';
import { EmptyState } from '@/components/ui/EmptyState';
import type { AnimalPublic, FilterState } from '@/types/animal';

interface AnimalGridProps {
  initialItems: AnimalPublic[];
  totalCount: number;
  filters: FilterState;
  pageSize?: number;
}

export function AnimalGrid({
  initialItems,
  totalCount,
  filters,
  pageSize = 20,
}: AnimalGridProps) {
  if (initialItems.length === 0) {
    // status='sheltered' は parseFilters のデフォルト適用で実質的なフィルタ
    // ではないため除外する。それ以外のフィルタ条件が指定されていれば
    // 「絞り込み 0 件」として案内し、無ければ「収集タイミング待ち」案内にする。
    const hasActiveFilters =
      Boolean(filters.category) ||
      Boolean(filters.species) ||
      Boolean(filters.sex) ||
      Boolean(filters.prefecture) ||
      Boolean(filters.location) ||
      Boolean(filters.q) ||
      Boolean(filters.status && filters.status !== 'sheltered');

    if (hasActiveFilters) {
      return (
        <EmptyState
          message="条件に合う動物が見つかりませんでした"
          suggestion="フィルタを変えるか、すべてクリアして再度お試しください。"
          showClearButton
        />
      );
    }
    return (
      <EmptyState
        message="現在表示できる動物がいません"
        suggestion="最新の収集データが反映されるまで少しお待ちください。収集は毎日自動で更新されます。"
      />
    );
  }

  const filtersKey = JSON.stringify(filters);

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
        {initialItems.map((animal) => (
          <AnimalCard key={animal.id} animal={animal} />
        ))}
      </div>

      <LoadMore
        key={filtersKey}
        initialOffset={initialItems.length}
        totalCount={totalCount}
        filters={filters}
        pageSize={pageSize}
      />
    </>
  );
}
