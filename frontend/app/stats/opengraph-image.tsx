import { ImageResponse } from 'next/og';

import { fetchPublicStats } from '@/lib/public-stats';

export const alt = 'oneco の実績 - 全国の保護動物プラットフォーム';
export const size = { width: 1200, height: 630 };
export const contentType = 'image/png';

export const revalidate = 300;

export default async function StatsOpengraphImage() {
  let totalAnimals = 0;
  let municipalities = 0;
  let siteCount = 0;
  try {
    const stats = await fetchPublicStats({ revalidateSec: 300 });
    totalAnimals = stats.total_animals;
    municipalities = stats.municipality_count;
    siteCount = stats.site_count;
  } catch {
    // ベストエフォート: 取得失敗時は 0 をそのまま表示する。
    // OG 画像生成に例外を投げない（SNS シェアで 500 を返さないため）。
  }

  return new ImageResponse(
    (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          background:
            'linear-gradient(135deg, #fff7ed 0%, #ffedd5 50%, #fed7aa 100%)',
          fontFamily: '"Hiragino Sans", "Yu Gothic", sans-serif',
          padding: 64,
        }}
      >
        <div
          style={{
            fontSize: 64,
            fontWeight: 700,
            color: '#9a3412',
            letterSpacing: '-0.02em',
            marginBottom: 16,
          }}
        >
          oneco の実績
        </div>
        <div
          style={{
            fontSize: 28,
            color: '#7c2d12',
            fontWeight: 500,
            marginBottom: 48,
            textAlign: 'center',
          }}
        >
          全国の保護動物情報を一つに
        </div>

        <div
          style={{
            display: 'flex',
            gap: 48,
            alignItems: 'flex-end',
          }}
        >
          <StatBlock
            value={totalAnimals.toLocaleString('ja-JP')}
            unit="頭"
            label="累計掲載動物"
          />
          <StatBlock
            value={municipalities.toLocaleString('ja-JP')}
            unit="都道府県"
            label="対応自治体"
          />
          <StatBlock
            value={siteCount.toLocaleString('ja-JP')}
            unit="サイト"
            label="対応サイト"
          />
        </div>

        <div
          style={{
            display: 'flex',
            gap: 12,
            marginTop: 48,
            fontSize: 28,
            color: '#9a3412',
            opacity: 0.7,
          }}
        >
          🐕 🐈
        </div>
      </div>
    ),
    size,
  );
}

function StatBlock({
  value,
  unit,
  label,
}: {
  value: string;
  unit: string;
  label: string;
}) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        minWidth: 240,
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          gap: 8,
          color: '#7c2d12',
        }}
      >
        <span
          style={{
            fontSize: 92,
            fontWeight: 700,
            lineHeight: 1,
          }}
        >
          {value}
        </span>
        <span style={{ fontSize: 28, fontWeight: 500 }}>{unit}</span>
      </div>
      <div
        style={{
          marginTop: 12,
          fontSize: 20,
          fontWeight: 500,
          color: '#9a3412',
          opacity: 0.85,
        }}
      >
        {label}
      </div>
    </div>
  );
}
