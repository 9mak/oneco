import type { ArchivedAnimalPublic, PaginatedResponse } from '@/types/animal';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

export interface FetchArchivedAnimalsParams {
  species?: '犬' | '猫';
  limit?: number;
  offset?: number;
}

export async function fetchArchivedAnimals(
  params: FetchArchivedAnimalsParams = {},
): Promise<PaginatedResponse<ArchivedAnimalPublic>> {
  const search = new URLSearchParams();
  search.set('limit', String(params.limit ?? 20));
  search.set('offset', String(params.offset ?? 0));
  if (params.species) search.set('species', params.species);

  const url = `${API_BASE_URL}/archive/animals?${search.toString()}`;
  const res = await fetch(url, {
    // ISR: 卒業データは更新頻度が低いので 30 分
    next: { revalidate: 1800 },
  });

  if (!res.ok) {
    throw new Error(`Failed to fetch archived animals: ${res.status}`);
  }
  return res.json();
}
