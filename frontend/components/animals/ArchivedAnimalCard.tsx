'use client';

import Image from 'next/image';
import { useState } from 'react';
import type { ArchivedAnimalPublic } from '@/types/animal';
import { PLACEHOLDER_IMAGE } from '@/lib/images';

interface ArchivedAnimalCardProps {
  animal: ArchivedAnimalPublic;
}

/**
 * 卒業した子（譲渡済 or 返還済）用のカード。
 *
 * 公開一覧（収容中）の AnimalCard と意図的に分離している:
 * - 詳細ページ・問い合わせ導線を持たない（既に新しい家族 or 元の家族の元）
 * - status バッジで成果（譲渡 / 飼い主の元へ）を可視化
 * - 卒業日を見出しに据える（収容日ではなく、成果が出た日）
 */
export function ArchivedAnimalCard({ animal }: ArchivedAnimalCardProps) {
  const [imgSrc, setImgSrc] = useState(animal.image_urls[0] || PLACEHOLDER_IMAGE);

  const outcomeDateStr = animal.outcome_date ?? animal.archived_at;
  const outcomeDate = new Date(outcomeDateStr).toLocaleDateString('ja-JP', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });

  const badgeLabel = animal.status === 'adopted' ? '譲渡' : '飼い主の元へ';
  const badgeClass =
    animal.status === 'adopted'
      ? 'bg-[var(--color-category-adoption)] text-white'
      : 'bg-[var(--color-accent-700)] text-white';

  return (
    <article className="bg-white rounded-lg shadow-md overflow-hidden">
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
          <span
            role="status"
            aria-label={`卒業: ${badgeLabel}`}
            className={`inline-flex items-center gap-1 px-3 py-1 rounded-full text-sm font-medium ${badgeClass}`}
          >
            <span aria-hidden="true">🎉</span>
            {badgeLabel}
          </span>
        </div>
      </div>

      <div className="p-4 space-y-2">
        <h3 className="text-lg font-semibold text-[var(--color-text-primary)]">
          {animal.species}
        </h3>

        <dl className="grid grid-cols-2 gap-2 text-sm">
          <div className="col-span-2">
            <dt className="text-[var(--color-text-secondary)]">性別</dt>
            <dd className="text-[var(--color-text-primary)] font-medium">{animal.sex}</dd>
          </div>
          <div className="col-span-2">
            <dt className="text-[var(--color-text-secondary)]">卒業日</dt>
            <dd className="text-[var(--color-text-primary)] font-medium">{outcomeDate}</dd>
          </div>
          <div className="col-span-2">
            <dt className="text-[var(--color-text-secondary)]">収容元</dt>
            <dd className="text-[var(--color-text-primary)] font-medium">{animal.location}</dd>
          </div>
        </dl>

        <p className="mt-3 text-xs text-[var(--color-text-secondary)] leading-relaxed">
          この子はすでに卒業しています。お問い合わせは受け付けていません。
        </p>
      </div>
    </article>
  );
}
