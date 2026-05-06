import type { MetadataRoute } from 'next';

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? 'http://localhost:3000';
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

interface SitemapAnimal {
  id: number;
  shelter_date: string;
  status_changed_at: string | null;
}

interface SitemapResponse {
  items: SitemapAnimal[];
  meta: { has_next: boolean };
}

async function fetchAllSitemapAnimals(): Promise<SitemapAnimal[]> {
  const PAGE_SIZE = 100;
  const all: SitemapAnimal[] = [];
  let offset = 0;

  try {
    while (true) {
      const url = `${API_BASE_URL}/animals?limit=${PAGE_SIZE}&offset=${offset}&status=sheltered`;
      const res = await fetch(url, { next: { revalidate: 3600 } });
      if (!res.ok) break;

      const data = (await res.json()) as SitemapResponse;
      all.push(...data.items);
      if (!data.meta.has_next) break;
      offset += PAGE_SIZE;
    }
  } catch (error) {
    // ビルド時に API へ到達できないケース（CI ビルド環境等）でも
    // 静的ルートのみで sitemap を生成して build を通す。runtime に
    // ISR で再生成されるので最終的に動物 URL も sitemap に乗る。
    console.warn('sitemap: failed to fetch animals, falling back to static routes only:', error);
  }

  return all;
}

export const revalidate = 3600;
// Vercel の build 時 prerender ではなく runtime に生成（API 未起動時のビルド失敗回避）
export const dynamic = 'force-dynamic';

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const animals = await fetchAllSitemapAnimals();

  const staticRoutes: MetadataRoute.Sitemap = [
    {
      url: SITE_URL,
      lastModified: new Date(),
      changeFrequency: 'daily',
      priority: 1.0,
    },
  ];

  const animalRoutes: MetadataRoute.Sitemap = animals.map((a) => ({
    url: `${SITE_URL}/animals/${a.id}`,
    lastModified: new Date(a.status_changed_at ?? a.shelter_date),
    changeFrequency: 'weekly',
    priority: 0.8,
  }));

  return [...staticRoutes, ...animalRoutes];
}
