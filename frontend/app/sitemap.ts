import type { MetadataRoute } from 'next';
import { PREFECTURES } from '@/lib/prefectures';
import { getSiteUrl } from '@/lib/site-url';
import { getApiBaseUrl } from '@/lib/api-base-url';

const SITE_URL = getSiteUrl();

interface SitemapAnimal {
  id: number;
  shelter_date: string;
  status_changed_at: string | null;
}

interface SitemapResponse {
  items: SitemapAnimal[];
  meta: { has_next: boolean; total_count: number };
}

async function fetchAnimalPage(offset: number, pageSize: number): Promise<SitemapResponse | null> {
  const url = `${getApiBaseUrl()}/animals?limit=${pageSize}&offset=${offset}&status=sheltered`;
  const res = await fetch(url, { next: { revalidate: 3600 } });
  if (!res.ok) return null;
  return (await res.json()) as SitemapResponse;
}

async function fetchAllSitemapAnimals(): Promise<SitemapAnimal[]> {
  const PAGE_SIZE = 100;

  try {
    // 1 ページ目で総数を確定させ、残りは並列取得する。
    // Google の sitemap クローラは遅い応答を「取得できませんでした」と扱う
    // ため、直列 12+ ラウンドトリップ (1000+ 件で 8 秒超) は事故りやすい
    // (2026-07-24 Search Console で発覚: 送信から40日超インデックス0件)。
    const first = await fetchAnimalPage(0, PAGE_SIZE);
    if (!first) return [];

    const all = [...first.items];
    const totalPages = Math.ceil(first.meta.total_count / PAGE_SIZE);

    if (totalPages > 1) {
      const remainingOffsets = Array.from({ length: totalPages - 1 }, (_, i) => (i + 1) * PAGE_SIZE);
      const remainingPages = await Promise.all(
        remainingOffsets.map((offset) => fetchAnimalPage(offset, PAGE_SIZE)),
      );
      for (const page of remainingPages) {
        if (page) all.push(...page.items);
      }
    }

    return all;
  } catch (error) {
    // ビルド時に API へ到達できないケース（CI ビルド環境等）でも
    // 静的ルートのみで sitemap を生成して build を通す。runtime に
    // ISR で再生成されるので最終的に動物 URL も sitemap に乗る。
    console.warn('sitemap: failed to fetch animals, falling back to static routes only:', error);
    return [];
  }
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
    {
      url: `${SITE_URL}/archive`,
      lastModified: new Date(),
      changeFrequency: 'weekly',
      priority: 0.6,
    },
    // インデックス対象の静的コンテンツページ (固有の title/description を持つ)。
    // 列挙漏れで検索に出ていなかった (2026-06-16 発覚)。
    {
      url: `${SITE_URL}/stats`,
      lastModified: new Date(),
      changeFrequency: 'daily',
      priority: 0.6,
    },
    {
      url: `${SITE_URL}/about`,
      lastModified: new Date(),
      changeFrequency: 'monthly',
      priority: 0.5,
    },
    {
      url: `${SITE_URL}/transparency`,
      lastModified: new Date(),
      changeFrequency: 'monthly',
      priority: 0.4,
    },
  ];

  // 都道府県別ランディング（地域×保護動物のローカル検索の受け皿）
  const areaRoutes: MetadataRoute.Sitemap = PREFECTURES.map((p) => ({
    url: `${SITE_URL}/areas/${encodeURIComponent(p)}`,
    lastModified: new Date(),
    changeFrequency: 'daily',
    priority: 0.7,
  }));

  const animalRoutes: MetadataRoute.Sitemap = animals.map((a) => ({
    url: `${SITE_URL}/animals/${a.id}`,
    lastModified: new Date(a.status_changed_at ?? a.shelter_date),
    changeFrequency: 'weekly',
    priority: 0.8,
  }));

  return [...staticRoutes, ...areaRoutes, ...animalRoutes];
}
