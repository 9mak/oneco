'use client';

import Link from 'next/link';
import Image from 'next/image';
import { useState } from 'react';
import { AnimalPublic } from '@/types/animal';
import { CategoryBadge } from '@/components/ui/CategoryBadge';
import { FavoriteButton } from '@/components/animals/FavoriteButton';

interface AnimalCardProps {
  animal: AnimalPublic;
}

const PLACEHOLDER_IMAGE = '/images/placeholder-animal.svg';

export function AnimalCard({ animal }: AnimalCardProps) {
  const ageDisplay = animal.age_months
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

  return (
    <Link
      href={`/animals/${animal.id}`}
      className="block bg-white rounded-lg shadow-md hover:shadow-lg transition-shadow overflow-hidden focus:outline-none focus:ring-2 focus:ring-[var(--color-focus-ring)] focus:ring-offset-2"
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
        <div className="absolute top-2 left-2">
          <FavoriteButton animalId={animal.id} size="sm" stopPropagation />
        </div>
      </div>

      <div className="p-4 space-y-2">
        <h3 className="text-lg font-semibold text-[var(--color-text-primary)]">
          {animal.species} / {animal.sex}
        </h3>

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
