/**
 * HomePage - トップページ (Server Component)
 * 初期動物一覧データをサーバーサイドフェッチし、SEO最適化されたHTMLを生成
 */

import { Suspense } from 'react';
import { AnimalListClient } from '@/components/animals/AnimalListClient';
import { AnimalPublic, PaginatedResponse } from '@/types/animal';

// ISR (Incremental Static Regeneration) - 10分ごとに再生成
export const revalidate = 600;

async function getInitialAnimals(): Promise<{
  animals: AnimalPublic[];
  totalCount: number;
}> {
  try {
    const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';
    const response = await fetch(`${baseUrl}/animals?limit=20&offset=0`, {
      next: { revalidate: 600 },
    });

    if (!response.ok) {
      // エラー時は空配列を返す
      return { animals: [], totalCount: 0 };
    }

    const data: PaginatedResponse<AnimalPublic> = await response.json();
    return {
      animals: data.items,
      totalCount: data.meta.total_count,
    };
  } catch (error) {
    console.error('Failed to fetch initial animals:', error);
    // エラー時は空配列を返す
    return { animals: [], totalCount: 0 };
  }
}

export default async function HomePage() {
  const { animals, totalCount } = await getInitialAnimals();

  return (
    <Suspense fallback={<div className="container mx-auto px-4 py-8">読み込み中...</div>}>
      <AnimalListClient initialAnimals={animals} initialTotalCount={totalCount} />
    </Suspense>
  );
}
