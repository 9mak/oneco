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
    const hasActiveFilters = Object.values(filters).some((v) => v !== undefined);
    return (
      <EmptyState
        message="現在表示できる動物がいません"
        showClearButton={hasActiveFilters}
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
