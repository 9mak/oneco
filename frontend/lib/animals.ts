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
