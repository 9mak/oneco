import { ImageResponse } from 'next/og';

export const alt = 'oneco - 保護動物詳細';
export const size = { width: 1200, height: 630 };
export const contentType = 'image/png';

interface AnimalSummary {
  species: string;
  sex: string;
  prefecture: string | null;
  location: string;
  category: string;
  size: string | null;
}

const CATEGORY_LABEL: Record<string, string> = {
  adoption: '譲渡対象',
  lost: '迷子',
  sheltered: '収容中',
};

async function fetchAnimal(id: string): Promise<AnimalSummary | null> {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';
  try {
    const res = await fetch(`${apiBaseUrl}/animals/${id}`, {
      next: { revalidate: 600 },
    });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export default async function AnimalOgImage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const animal = await fetchAnimal(id);

  if (!animal) {
    return new ImageResponse(
      (
        <div
          style={{
            width: '100%',
            height: '100%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'linear-gradient(135deg, #fff7ed 0%, #fed7aa 100%)',
            fontFamily: '"Hiragino Sans", "Yu Gothic", sans-serif',
          }}
        >
          <div style={{ fontSize: 64, fontWeight: 700, color: '#9a3412' }}>oneco</div>
        </div>
      ),
      size,
    );
  }

  const speciesEmoji = animal.species === '犬' ? '🐕' : animal.species === '猫' ? '🐈' : '🐾';
  const categoryLabel = CATEGORY_LABEL[animal.category] ?? animal.category;
  const region = animal.prefecture ?? animal.location.slice(0, 12);

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
          background: 'linear-gradient(135deg, #fff7ed 0%, #ffedd5 50%, #fed7aa 100%)',
          fontFamily: '"Hiragino Sans", "Yu Gothic", sans-serif',
          padding: 60,
        }}
      >
        <div style={{ fontSize: 200, marginBottom: 16 }}>{speciesEmoji}</div>
        <div style={{ fontSize: 64, fontWeight: 700, color: '#9a3412', marginBottom: 16 }}>
          {region}の{animal.species}
        </div>
        <div
          style={{ display: 'flex', gap: 16, fontSize: 28, color: '#7c2d12', marginBottom: 24 }}
        >
          <span
            style={{
              padding: '6px 16px',
              background: '#fb923c',
              color: 'white',
              borderRadius: 999,
              fontSize: 24,
            }}
          >
            {categoryLabel}
          </span>
          {animal.sex && animal.sex !== '不明' && (
            <span
              style={{
                padding: '6px 16px',
                background: 'white',
                color: '#9a3412',
                borderRadius: 999,
                border: '2px solid #fb923c',
                fontSize: 24,
              }}
            >
              {animal.sex}
            </span>
          )}
          {animal.size && (
            <span
              style={{
                padding: '6px 16px',
                background: 'white',
                color: '#9a3412',
                borderRadius: 999,
                border: '2px solid #fb923c',
                fontSize: 24,
              }}
            >
              {animal.size}
            </span>
          )}
        </div>
        <div style={{ fontSize: 28, color: '#9a3412', opacity: 0.7, marginTop: 32 }}>
          oneco — 全国の保護動物を一つに
        </div>
      </div>
    ),
    size,
  );
}
