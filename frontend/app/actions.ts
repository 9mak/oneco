'use server';

import { fetchAnimals, type FetchAnimalsParams } from '@/lib/animals';

export async function loadMoreAnimals(params: FetchAnimalsParams) {
  return fetchAnimals(params);
}
