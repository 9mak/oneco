import { ImageResponse } from 'next/og';
import { getApiBaseUrl } from '@/lib/api-base-url';
import { isValidPrefecture } from '@/lib/prefectures';

export const alt = 'oneco - 都道府県別の保護動物一覧';
export const size = { width: 1200, height: 630 };
export const contentType = 'image/png';

const FONT_FAMILY = 'Noto Sans JP';

function resolvePrefecture(raw: string): string | null {
  let decoded: string;
  try {
    decoded = decodeURIComponent(raw);
  } catch {
    return null;
  }
  return isValidPrefecture(decoded) ? decoded : null;
}

async function fetchTotalCount(prefecture: string): Promise<number | null> {
  const apiBaseUrl = getApiBaseUrl();
  try {
    const res = await fetch(
      `${apiBaseUrl}/animals?prefecture=${encodeURIComponent(prefecture)}&status=sheltered&limit=1&offset=0`,
      { next: { revalidate: 600 } },
    );
    if (!res.ok) return null;
    const data = (await res.json()) as { meta: { total_count: number } };
    return data.meta.total_count;
  } catch {
    return null;
  }
}

/**
 * next/og (Satori) は CJK グリフを持つフォントを明示的に渡さないと、
 * 日本語を含む OG 画像生成時に例外を投げて HTTP 500 になる (animals/[id] と同じ制約)。
 */
async function loadGoogleFont(text: string, weight: number): Promise<ArrayBuffer | null> {
  const family = `Noto Sans JP:wght@${weight}`;
  const url = `https://fonts.googleapis.com/css2?family=${encodeURIComponent(family)}&text=${encodeURIComponent(text)}`;
  try {
    const cssRes = await fetch(url, {
      headers: {
        'User-Agent':
          'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
      },
      next: { revalidate: 86400 },
    });
    if (!cssRes.ok) return null;
    const css = await cssRes.text();
    const match = css.match(/src:\s*url\((.+?)\)\s*format\('(?:opentype|truetype)'\)/);
    if (!match) return null;
    const fontRes = await fetch(match[1], { next: { revalidate: 86400 } });
    if (!fontRes.ok) return null;
    return await fontRes.arrayBuffer();
  } catch {
    return null;
  }
}

function fallbackImage(): ImageResponse {
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
        }}
      >
        <div style={{ fontSize: 64, fontWeight: 700, color: '#9a3412' }}>oneco</div>
      </div>
    ),
    size,
  );
}

export default async function AreaOgImage({
  params,
}: {
  params: Promise<{ prefecture: string }>;
}) {
  const { prefecture: raw } = await params;
  const pref = resolvePrefecture(raw);

  if (!pref) {
    return fallbackImage();
  }

  const totalCount = await fetchTotalCount(pref);
  const countLabel = totalCount !== null ? `${totalCount}頭掲載中` : '保護犬・保護猫を掲載中';

  // 実際に描画する全文字をサブセット要求に含める（動的な都道府県名を含む）。
  const ogText = `${pref}の保護犬・保護猫一覧${countLabel}oneco — 全国の保護動物を一つに`;

  const [regular, bold] = await Promise.all([
    loadGoogleFont(ogText, 400),
    loadGoogleFont(ogText, 700),
  ]);

  if (!regular || !bold) {
    return fallbackImage();
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
          background: 'linear-gradient(135deg, #fff7ed 0%, #ffedd5 50%, #fed7aa 100%)',
          fontFamily: FONT_FAMILY,
          padding: 60,
        }}
      >
        <div style={{ fontSize: 96, marginBottom: 16 }}>🐕🐈</div>
        <div style={{ fontSize: 72, fontWeight: 700, color: '#9a3412', marginBottom: 16 }}>
          {pref}
        </div>
        <div style={{ fontSize: 40, fontWeight: 700, color: '#7c2d12', marginBottom: 24 }}>
          保護犬・保護猫の里親募集一覧
        </div>
        <div
          style={{
            padding: '10px 28px',
            background: '#fb923c',
            color: 'white',
            borderRadius: 999,
            fontSize: 32,
            marginBottom: 32,
          }}
        >
          {countLabel}
        </div>
        <div style={{ fontSize: 28, color: '#9a3412', opacity: 0.7 }}>
          oneco — 全国の保護動物を一つに
        </div>
      </div>
    ),
    {
      ...size,
      emoji: 'twemoji',
      fonts: [
        { name: FONT_FAMILY, data: regular, weight: 400, style: 'normal' },
        { name: FONT_FAMILY, data: bold, weight: 700, style: 'normal' },
      ],
    },
  );
}
