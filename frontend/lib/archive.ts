import type { ArchivedAnimalPublic, PaginatedResponse } from '@/types/animal';
import { getApiBaseUrl } from '@/lib/api-base-url';

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

  const url = `${getApiBaseUrl()}/archive/animals?${search.toString()}`;
  const res = await fetch(url, {
    // ISR: 卒業データは更新頻度が低いので 30 分
    next: { revalidate: 1800 },
  });

  if (!res.ok) {
    throw new Error(`Failed to fetch archived animals: ${res.status}`);
  }
  return res.json();
}
