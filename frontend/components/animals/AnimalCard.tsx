'use client';

import Link from 'next/link';
import Image from 'next/image';
import { useState } from 'react';
import { AnimalPublic } from '@/types/animal';
import { CategoryBadge } from '@/components/ui/CategoryBadge';
import { FavoriteButton } from '@/components/animals/FavoriteButton';
import { StaleDataBadge } from '@/components/animals/StaleDataBadge';
import { PLACEHOLDER_IMAGE } from '@/lib/images';

interface AnimalCardProps {
  animal: AnimalPublic;
}

export function AnimalCard({ animal }: AnimalCardProps) {
  const ageDisplay =
    animal.age_months != null
      ? animal.age_months >= 12
      ? `${Math.floor(animal.age_months / 12)}歳`
      : `${animal.age_months}ヶ月`
    : '不明';

  const initialSrc = animal.image_urls[0] || PLACEHOLDER_IMAGE;
  const [imgSrc, setImgSrc] = useState(initialSrc);

  const shelterDate = new Date(animal.shelter_date).toLocaleDateString('ja-JP', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });

  // <a> の中に <button> を置くのは無効な HTML (interactive content モデル違反)。
  // <article> を外枠にして Link と FavoriteButton を兄弟要素に分離する。
  return (
    <article className="relative bg-white rounded-lg shadow-md hover:shadow-lg transition-shadow overflow-hidden">
      <Link
        href={`/animals/${animal.id}`}
        className="block focus:outline-none focus:ring-2 focus:ring-[var(--color-focus-ring)] focus:ring-offset-2 rounded-lg"
      >
        <div className="relative w-full h-48 bg-gray-200">
          <Image
            src={imgSrc}
            alt={`${animal.species}の画像`}
            fill
            className="object-cover"
            sizes="(max-width: 767px) 100vw, (max-width: 1023px) 50vw, 33vw"
            loading="lazy"
            unoptimized={imgSrc === PLACEHOLDER_IMAGE ? true : undefined}
            onError={() => setImgSrc(PLACEHOLDER_IMAGE)}
          />
          <div className="absolute top-2 right-2">
            <CategoryBadge category={animal.category} size="sm" />
          </div>
        </div>

        <div className="p-4 space-y-2">
          <div className="flex items-start justify-between gap-2">
            <h3 className="text-lg font-semibold text-[var(--color-text-primary)]">
              {animal.sex === '不明' ? animal.species : `${animal.species}の${animal.sex}`}
            </h3>
            <StaleDataBadge shelterDate={animal.shelter_date} />
          </div>

          <dl className="grid grid-cols-2 gap-2 text-sm">
            <div>
              <dt className="text-[var(--color-text-secondary)]">推定年齢</dt>
              <dd className="text-[var(--color-text-primary)] font-medium">{ageDisplay}</dd>
            </div>
            {animal.color && (
              <div>
                <dt className="text-[var(--color-text-secondary)]">毛色</dt>
                <dd className="text-[var(--color-text-primary)] font-medium">{animal.color}</dd>
              </div>
            )}
            {animal.size && (
              <div>
                <dt className="text-[var(--color-text-secondary)]">体格</dt>
                <dd className="text-[var(--color-text-primary)] font-medium">{animal.size}</dd>
              </div>
            )}
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

      {/* お気に入りボタン: Link の兄弟として後ろに置き、a>button ネストを避けつつ
          タブ順を「カード本体 → お気に入り」にする。視覚配置は absolute で左上に固定。 */}
      <div className="absolute top-2 left-2 z-10">
        <FavoriteButton animalId={animal.id} size="sm" />
      </div>
    </article>
  );
}
