import { Suspense } from 'react';
import { fetchAnimals } from '@/lib/animals';
import { AnimalGrid } from '@/components/animals/AnimalGrid';
import { FilterPanel } from '@/components/animals/FilterPanel';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';
import type { AnimalPublic, FilterState } from '@/types/animal';

export const revalidate = 300;

interface HomePageProps {
  searchParams: Promise<{
    species?: string;
    sex?: string;
    location?: string;
    category?: string;
  }>;
}

const PAGE_SIZE = 20;

function parseFilters(params: Awaited<HomePageProps['searchParams']>): FilterState {
  const filters: FilterState = {};
  if (params.species === '犬' || params.species === '猫') {
    filters.species = params.species;
  }
  if (params.sex === '男の子' || params.sex === '女の子' || params.sex === '不明') {
    filters.sex = params.sex;
  }
  if (
    params.category === 'adoption' ||
    params.category === 'lost' ||
    params.category === 'sheltered'
  ) {
    filters.category = params.category;
  }
  if (params.location) {
    filters.location = params.location;
  }
  return filters;
}

async function AnimalsSection({ filters }: { filters: FilterState }) {
  let items: AnimalPublic[] = [];
  let totalCount = 0;
  try {
    const data = await fetchAnimals({ ...filters, limit: PAGE_SIZE, offset: 0 });
    items = data.items;
    totalCount = data.meta.total_count;
  } catch (error) {
    console.error('Failed to fetch animals:', error);
  }

  return (
    <div className="container mx-auto px-4 py-8 space-y-8">
      <FilterPanel filters={filters} resultCount={totalCount} />
      <AnimalGrid
        initialItems={items}
        totalCount={totalCount}
        filters={filters}
        pageSize={PAGE_SIZE}
      />
    </div>
  );
}

export default async function HomePage({ searchParams }: HomePageProps) {
  const params = await searchParams;
  const filters = parseFilters(params);

  return (
    <Suspense
      key={JSON.stringify(filters)}
      fallback={
        <div className="container mx-auto px-4 py-8">
          <LoadingSpinner />
        </div>
      }
    >
      <AnimalsSection filters={filters} />
    </Suspense>
  );
}
