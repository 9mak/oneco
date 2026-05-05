import type { AnimalPublic } from '@/types/animal';

interface PetSchemaProps {
  animal: AnimalPublic;
  siteUrl: string;
}

/**
 * 動物個体ページの構造化データ (JSON-LD)
 *
 * schema.org/Article をベースに、about プロパティで Pet/Animal の
 * 詳細を埋め込む。Google の Rich Results 対応 + 検索結果でのスニペット改善。
 */
export function PetSchema({ animal, siteUrl }: PetSchemaProps) {
  const categoryLabel =
    animal.category === 'adoption'
      ? '譲渡対象'
      : animal.category === 'lost'
        ? '迷子情報'
        : '収容中';

  const headline = `${animal.prefecture ?? ''} ${animal.location}の${animal.species}（${categoryLabel}）`.trim();
  const url = `${siteUrl}/animals/${animal.id}`;

  const data = {
    '@context': 'https://schema.org',
    '@type': 'Article',
    headline,
    description: `${animal.location}で保護された${animal.species}の情報。${categoryLabel}として登録されています。`,
    image: animal.image_urls.length > 0 ? animal.image_urls : undefined,
    datePublished: animal.shelter_date,
    url,
    mainEntityOfPage: {
      '@type': 'WebPage',
      '@id': url,
    },
    about: {
      '@type': 'Pet',
      name: `${animal.location}の${animal.species}`,
      animal: {
        '@type': 'Animal',
        ...(animal.color && { additionalProperty: { '@type': 'PropertyValue', name: '毛色', value: animal.color } }),
      },
      ...(animal.image_urls.length > 0 && { image: animal.image_urls[0] }),
      ...(animal.color && { color: animal.color }),
      ...(animal.sex && { gender: animal.sex }),
    },
    locationCreated: {
      '@type': 'Place',
      name: animal.location,
      ...(animal.prefecture && {
        address: {
          '@type': 'PostalAddress',
          addressRegion: animal.prefecture,
          addressLocality: animal.location,
          addressCountry: 'JP',
        },
      }),
    },
  };

  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(data) }}
    />
  );
}

interface OrganizationSchemaProps {
  siteUrl: string;
  siteName: string;
}

/**
 * サイト全体の Organization 構造化データ
 *
 * Google 検索のナレッジパネル候補・ブランド認識のため layout.tsx に配置する。
 */
export function OrganizationSchema({ siteUrl, siteName }: OrganizationSchemaProps) {
  const data = {
    '@context': 'https://schema.org',
    '@type': 'Organization',
    name: siteName,
    url: siteUrl,
    description:
      '全国の自治体に保護されている犬・猫の情報を一元化したポータルサイト。譲渡対象動物・迷子情報を都道府県別・条件別に検索できます。',
    sameAs: ['https://github.com/9mak/oneco'],
  };

  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(data) }}
    />
  );
}
