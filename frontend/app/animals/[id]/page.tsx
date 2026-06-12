/**
 * Animal Detail Page (Server Component)
 * 個別動物データをサーバーサイドでフェッチし、SEO最適化されたHTMLを生成
 * Requirements: 2.1, 2.2, 2.8
 */

import { notFound } from 'next/navigation';
import { AnimalPublic } from '@/types/animal';
import { AnimalDetailClient } from '@/components/animals/AnimalDetailClient';
import { PetSchema } from '@/components/animals/PetSchema';
import { getSiteUrl } from '@/lib/site-url';

const SITE_URL = getSiteUrl();

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

  // a11y: layout.tsx で <main> ランドマークを出しているためここでは <section>。
  // h1 は AnimalDetailClient が持つので sr-only h1 は重複回避のため削除。
  // title はメタデータ生成側で利用される。
  void title;
  return (
    <section className="min-h-screen bg-gray-50">
      <PetSchema animal={animal} siteUrl={SITE_URL} />
      <div className="container mx-auto px-4 py-8">
        <AnimalDetailClient animal={animal} />
      </div>
    </section>
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
    const region = animal.prefecture
      ? `${animal.prefecture}${animal.location && animal.location !== animal.prefecture ? ` ${animal.location}` : ''}`
      : animal.location;
    const identifier = animal.name
      ? `「${animal.name}」`
      : animal.management_number
        ? `（管理番号: ${animal.management_number}）`
        : '';
    const title = `${animal.species}${identifier} - ${region}の${categoryLabel}`;

    const traits: string[] = [];
    if (animal.breed) traits.push(animal.breed);
    if (animal.sex && animal.sex !== '不明') traits.push(animal.sex);
    if (animal.size) traits.push(animal.size);
    if (animal.color) traits.push(`毛色: ${animal.color}`);
    if (animal.age_months !== null && animal.age_months !== undefined) {
      const years = Math.floor(animal.age_months / 12);
      traits.push(years > 0 ? `推定${years}歳` : `推定${animal.age_months}ヶ月`);
    }
    const traitText = traits.length ? traits.join('・') : animal.sex;
    const tail = animal.prefecture ? `${animal.prefecture}公式情報の集約。` : '公式情報の集約。';
    const description = `${region}で保護されている${animal.species}（${traitText}）。${tail} ${categoryLabel}として登録されています。`;

    const canonicalPath = `/animals/${animal.id}`;

    // OG 画像は同階層の opengraph-image.tsx で動的生成（元サイトURL依存を解消）
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
      },
      twitter: {
        card: 'summary_large_image',
        title,
        description,
      },
    };
  } catch {
    return {
      title: '動物詳細',
    };
  }
}
