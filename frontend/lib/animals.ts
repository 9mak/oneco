import type { AnimalPublic, FilterState, PaginatedResponse } from '@/types/animal';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

export interface FetchAnimalsParams extends FilterState {
  limit?: number;
  offset?: number;
}

function buildQuery(params: FetchAnimalsParams): string {
  const search = new URLSearchParams();
  search.set('limit', String(params.limit ?? 20));
  search.set('offset', String(params.offset ?? 0));
  if (params.species) search.set('species', params.species);
  if (params.sex) search.set('sex', params.sex);
  if (params.location) search.set('location', params.location);
  if (params.prefecture) search.set('prefecture', params.prefecture);
  if (params.category) search.set('category', params.category);
  if (params.status) search.set('status', params.status);
  if (params.q) search.set('q', params.q);
  return search.toString();
}

export async function fetchAnimals(
  params: FetchAnimalsParams,
): Promise<PaginatedResponse<AnimalPublic>> {
  const url = `${API_BASE_URL}/animals?${buildQuery(params)}`;
  const res = await fetch(url, {
    next: { revalidate: 300 },
  });

  if (!res.ok) {
    throw new Error(`Failed to fetch animals: ${res.status}`);
  }

  return res.json();
}

/**
 * 都道府県別の保護動物数を取得（status='sheltered' のみ集計）
 */
export async function fetchPrefectureStats(): Promise<Record<string, number>> {
  try {
    const res = await fetch(`${API_BASE_URL}/animals/stats/by-prefecture`, {
      next: { revalidate: 600 },
    });
    if (!res.ok) return {};
    return res.json();
  } catch {
    return {};
  }
}
