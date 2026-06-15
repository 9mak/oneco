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

const FONT_FAMILY = 'Noto Sans JP';

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

/**
 * next/og (Satori) は CJK グリフを持つフォントを明示的に渡さないと、
 * 日本語を含む OG 画像生成時に例外を投げて HTTP 500 になる。
 * Google Fonts の text サブセット API で、実際に描画する文字だけを含む
 * 軽量な Noto Sans JP を取得して渡す。
 */
async function loadGoogleFont(text: string, weight: number): Promise<ArrayBuffer | null> {
  const family = `Noto Sans JP:wght@${weight}`;
  const url = `https://fonts.googleapis.com/css2?family=${encodeURIComponent(family)}&text=${encodeURIComponent(text)}`;
  try {
    const cssRes = await fetch(url, {
      // CSS は user-agent によって返す形式が変わる。woff2 ではなく
      // Satori が扱える truetype/opentype を引くため一般的な UA を装う。
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
        {/* Latin のみ。デフォルトフォントで描画できるためフォント不要 */}
        <div style={{ fontSize: 64, fontWeight: 700, color: '#9a3412' }}>oneco</div>
      </div>
    ),
    size,
  );
}

export default async function AnimalOgImage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const animal = await fetchAnimal(id);

  if (!animal) {
    return fallbackImage();
  }

  const speciesEmoji = animal.species === '犬' ? '🐕' : animal.species === '猫' ? '🐈' : '🐾';
  const categoryLabel = CATEGORY_LABEL[animal.category] ?? animal.category;
  const region = animal.prefecture ?? animal.location.slice(0, 12);
  const sexLabel = animal.sex && animal.sex !== '不明' ? animal.sex : '';
  const sizeLabel = animal.size ?? '';

  // 実際に描画する全文字をサブセット要求に含める（動的な地域名・種別を含む）。
  const ogText = `${region}の${animal.species}${categoryLabel}${sexLabel}${sizeLabel}oneco — 全国の保護動物を一つに`;

  const [regular, bold] = await Promise.all([
    loadGoogleFont(ogText, 400),
    loadGoogleFont(ogText, 700),
  ]);

  // フォント取得に失敗したら 500 を返さず Latin フォールバックに退避する。
  // フォントさえ揃えば、描画する全文字はサブセットに含まれ絵文字は twemoji で
  // 解決されるため Satori はグリフ不足で例外を投げない（try/catch では
  // ImageResponse の遅延レンダリング例外を捕捉できないため事前ガードで担保する）。
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
        <div style={{ fontSize: 200, marginBottom: 16 }}>{speciesEmoji}</div>
        <div style={{ fontSize: 64, fontWeight: 700, color: '#9a3412', marginBottom: 16 }}>
          {region}の{animal.species}
        </div>
        <div style={{ display: 'flex', gap: 16, fontSize: 28, color: '#7c2d12', marginBottom: 24 }}>
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
          {sexLabel && (
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
              {sexLabel}
            </span>
          )}
          {sizeLabel && (
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
              {sizeLabel}
            </span>
          )}
        </div>
        <div style={{ fontSize: 28, color: '#9a3412', opacity: 0.7, marginTop: 32 }}>
          oneco — 全国の保護動物を一つに
        </div>
      </div>
    ),
    {
      ...size,
      // 絵文字 🐕🐈🐾 はフォントに含まれないため twemoji の SVG で描画する。
      emoji: 'twemoji',
      fonts: [
        { name: FONT_FAMILY, data: regular, weight: 400, style: 'normal' },
        { name: FONT_FAMILY, data: bold, weight: 700, style: 'normal' },
      ],
    },
  );
}
