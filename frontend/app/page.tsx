import { Suspense } from 'react';
import { fetchAnimals, fetchPrefectureStats } from '@/lib/animals';
import { AnimalGrid } from '@/components/animals/AnimalGrid';
import { AnimalGridSkeleton } from '@/components/animals/AnimalGridSkeleton';
import { FilterPanel } from '@/components/animals/FilterPanel';
import { PrefectureMap } from '@/components/animals/PrefectureMap';
import type { AnimalPublic, FilterState } from '@/types/animal';

export const revalidate = 300;

interface HomePageProps {
  searchParams: Promise<{
    species?: string;
    sex?: string;
    prefecture?: string;
    location?: string;
    category?: string;
    status?: string;
    q?: string;
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
  // status は未指定時 'sheltered'（収容中）を暗黙適用。譲渡済等は明示指定で表示
  if (
    params.status === 'sheltered' ||
    params.status === 'adopted' ||
    params.status === 'returned' ||
    params.status === 'deceased'
  ) {
    filters.status = params.status;
  } else {
    filters.status = 'sheltered';
  }
  if (params.prefecture) {
    filters.prefecture = params.prefecture;
  }
  if (params.location) {
    filters.location = params.location;
  }
  if (params.q && params.q.trim()) {
    filters.q = params.q.trim().slice(0, 100);
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
    <>
      <FilterPanel filters={filters} resultCount={totalCount} />
      <AnimalGrid
        initialItems={items}
        totalCount={totalCount}
        filters={filters}
        pageSize={PAGE_SIZE}
      />
    </>
  );
}

function FilterPanelSkeleton({ filters }: { filters: FilterState }) {
  return <FilterPanel filters={filters} resultCount={0} />;
}

async function PrefectureMapSection() {
  const counts = await fetchPrefectureStats();
  return <PrefectureMap countsByPrefecture={counts} />;
}

export default async function HomePage({ searchParams }: HomePageProps) {
  const params = await searchParams;
  const filters = parseFilters(params);

  return (
    <div className="container mx-auto px-4 py-8 space-y-8">
      {/* 都道府県別マップ（フィルター無し時のみ表示） */}
      {!filters.prefecture && (
        <Suspense fallback={<div className="bg-white rounded-lg shadow-md p-6 h-64 animate-pulse" />}>
          <PrefectureMapSection />
        </Suspense>
      )}

      <Suspense
        key={JSON.stringify(filters)}
        fallback={
          <>
            <FilterPanelSkeleton filters={filters} />
            <AnimalGridSkeleton />
          </>
        }
      >
        <AnimalsSection filters={filters} />
      </Suspense>
    </div>
  );
}
