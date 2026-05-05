/**
 * Animal Detail Page (Server Component)
 * 個別動物データをサーバーサイドでフェッチし、SEO最適化されたHTMLを生成
 * Requirements: 2.1, 2.2, 2.8
 */

import { notFound } from 'next/navigation';
import { AnimalPublic } from '@/types/animal';
import { AnimalDetailClient } from '@/components/animals/AnimalDetailClient';

interface AnimalDetailPageProps {
  params: Promise<{
    id: string;
  }>;
}

/**
 * 個別動物データを取得
 */
async function getAnimal(id: string): Promise<AnimalPublic | null> {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

  try {
    const res = await fetch(`${apiBaseUrl}/animals/${id}`, {
      // ISR: 10分ごとに再生成
      next: { revalidate: 600 },
    });

    if (!res.ok) {
      if (res.status === 404) {
        return null;
      }
      throw new Error(`Failed to fetch animal: ${res.status}`);
    }

    return res.json();
  } catch (error) {
    console.error('Error fetching animal:', error);
    throw error;
  }
}

/**
 * 動物詳細ページ
 */
export default async function AnimalDetailPage({ params }: AnimalDetailPageProps) {
  const { id } = await params;

  // IDの型安全性を確保（number型）
  const animalId = parseInt(id, 10);
  if (isNaN(animalId)) {
    notFound();
  }

  // 個別動物データをサーバーサイドフェッチ
  const animal = await getAnimal(id);

  // 存在しないIDの場合、404エラーページにリダイレクト
  if (!animal) {
    notFound();
  }

  // メタデータ用のタイトル生成
  const title = `${animal.species} - ${animal.location}`;

  return (
    <main className="min-h-screen bg-gray-50">
      <div className="container mx-auto px-4 py-8">
        <h1 className="sr-only">{title}</h1>
        <AnimalDetailClient animal={animal} />
      </div>
    </main>
  );
}

/**
 * 動的メタデータ生成（SEO最適化）
 */
export async function generateMetadata({ params }: AnimalDetailPageProps) {
  const { id } = await params;

  try {
    const animal = await getAnimal(id);

    if (!animal) {
      return {
        title: '動物が見つかりません',
      };
    }

    const categoryLabel =
      animal.category === 'adoption'
        ? '譲渡対象'
        : animal.category === 'lost'
          ? '迷子情報'
          : '収容中';
    const prefix = animal.prefecture ? `${animal.prefecture} ` : '';
    const title = `${prefix}${animal.location}の${animal.species}（${categoryLabel}）`;
    const sizeText = animal.size ? `・${animal.size}` : '';
    const ageText = animal.age_months ? `・推定${animal.age_months}ヶ月` : '';
    const description = `${animal.location}で保護された${animal.species}（${animal.sex}${sizeText}${ageText}）の詳細情報。${categoryLabel}として登録されています。`;

    const ogImage = animal.image_urls?.[0];
    const canonicalPath = `/animals/${animal.id}`;

    return {
      title,
      description,
      alternates: {
        canonical: canonicalPath,
      },
      openGraph: {
        type: 'article',
        title,
        description,
        url: canonicalPath,
        ...(ogImage && {
          images: [
            {
              url: ogImage,
              alt: `${animal.species}（${animal.location}）`,
            },
          ],
        }),
      },
      twitter: {
        card: ogImage ? 'summary_large_image' : 'summary',
        title,
        description,
        ...(ogImage && { images: [ogImage] }),
      },
    };
  } catch {
    return {
      title: '動物詳細',
    };
  }
}
