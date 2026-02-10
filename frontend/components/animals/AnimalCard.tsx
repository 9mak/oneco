/**
 * AnimalCard Component
 * 動物カード表示、Next.js Linkでルーティング、レスポンシブデザイン
 */

'use client';

import Link from 'next/link';
import Image from 'next/image';
import { AnimalPublic } from '@/types/animal';
import { CategoryBadge } from '@/components/ui/CategoryBadge';

interface AnimalCardProps {
  animal: AnimalPublic;
}

export function AnimalCard({ animal }: AnimalCardProps) {
  // 年齢を月から年に変換
  const ageDisplay = animal.age_months
    ? animal.age_months >= 12
      ? `${Math.floor(animal.age_months / 12)}歳`
      : `${animal.age_months}ヶ月`
    : '不明';

  // 代表画像（最初の画像）
  const imageUrl = animal.image_urls[0] || '/images/placeholder-animal.jpg';

  // 収容日をフォーマット
  const shelterDate = new Date(animal.shelter_date).toLocaleDateString('ja-JP', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });

  return (
    <Link
      href={`/animals/${animal.id}`}
      className="block bg-white rounded-lg shadow-md hover:shadow-lg transition-shadow overflow-hidden focus:outline-none focus:ring-2 focus:ring-[var(--color-focus-ring)] focus:ring-offset-2"
    >
      {/* 画像エリア */}
      <div className="relative w-full h-48 bg-gray-200">
        <Image
          src={imageUrl}
          alt={`${animal.species}の画像`}
          fill
          className="object-cover"
          sizes="(max-width: 767px) 100vw, (max-width: 1023px) 50vw, 33vw"
          loading="lazy"
        />
        {/* カテゴリバッジ */}
        <div className="absolute top-2 right-2">
          <CategoryBadge category={animal.category} size="sm" />
        </div>
      </div>

      {/* 情報エリア */}
      <div className="p-4 space-y-2">
        {/* 種別と性別 */}
        <h3 className="text-lg font-semibold text-[var(--color-text-primary)]">
          {animal.species} / {animal.sex}
        </h3>

        {/* 詳細情報 */}
        <dl className="grid grid-cols-2 gap-2 text-sm">
          <div>
            <dt className="text-[var(--color-text-secondary)]">推定年齢</dt>
            <dd className="text-[var(--color-text-primary)] font-medium">{ageDisplay}</dd>
          </div>
          <div>
            <dt className="text-[var(--color-text-secondary)]">収容日</dt>
            <dd className="text-[var(--color-text-primary)] font-medium">{shelterDate}</dd>
          </div>
          <div className="col-span-2">
            <dt className="text-[var(--color-text-secondary)]">収容場所</dt>
            <dd className="text-[var(--color-text-primary)] font-medium">{animal.location}</dd>
          </div>
        </dl>
      </div>
    </Link>
  );
}
