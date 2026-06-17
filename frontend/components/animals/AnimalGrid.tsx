import { AnimalCard } from './AnimalCard';
import { LoadMore } from './LoadMore';
import { EmptyState } from '@/components/ui/EmptyState';
import type { AnimalPublic, FilterState } from '@/types/animal';

interface AnimalGridProps {
  initialItems: AnimalPublic[];
  totalCount: number;
  filters: FilterState;
  pageSize?: number;
  /** API取得が失敗したか。true の場合は「0件」ではなく障害として案内する */
  fetchFailed?: boolean;
}

export function AnimalGrid({
  initialItems,
  totalCount,
  filters,
  pageSize = 20,
  fetchFailed = false,
}: AnimalGridProps) {
  // API取得失敗は「0件」と明確に区別して案内する（障害の可視化）
  if (fetchFailed) {
    return (
      <EmptyState
        message="現在情報を取得できません"
        suggestion="一時的な障害が発生している可能性があります。少し時間をおいて再度お試しください。"
      />
    );
  }

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
      <p
        className="text-sm text-[var(--color-text-secondary)]"
        aria-live="polite"
        aria-atomic="true"
      >
        <span className="font-medium text-[var(--color-text-primary)]">
          {totalCount.toLocaleString('ja-JP')}
        </span>
        件の動物
      </p>

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
