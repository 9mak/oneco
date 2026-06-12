# oneco の OGP 画像をリブランディングしてほしい

> このファイルは Codex（or 他のコーディングエージェント）に渡す依頼プロンプトです。
> 使い方: `cat docs/codex-prompts/ogp-redesign.md | pbcopy` でクリップボードに一括コピーし、Codex に貼り付けてください。

---

## プロジェクト前提

- **oneco** は全国の自治体に保護されている犬・猫の情報を一元化した非営利ポータルサイト
- 使命: 殺処分ゼロ。譲渡先を探す里親候補と保護動物のマッチング
- 本番URL: https://frontend-psi-ten-73.vercel.app
- 技術: Next.js 16 (App Router) + Tailwind + TypeScript strict mode
- 公開直後で、これから集客フェーズに入る（SNS シェア・プレス露出を増やしたい）

## OGP 画像の現状（要改善）

3 種類の OGP 画像が `next/og` の `ImageResponse` で生成されている。レイアウトはコード生成（SVG-like）。

1. **`frontend/app/opengraph-image.tsx`** — トップページ用（静的）
2. **`frontend/app/stats/opengraph-image.tsx`** — `/stats` 用（累計頭数・対応自治体数を動的表示）
3. **`frontend/app/animals/[id]/opengraph-image.tsx`** — 動物詳細用（個別の動物情報を動的表示）

### 現状の問題

- グラデーション背景＋oneco 文字＋小さな絵文字 (🐕🐈) だけで **視覚インパクトが弱い**
- 「保護動物ポータル」「殺処分ゼロ」のメッセージが **一目で伝わらない**
- ブランドカラー（オレンジ系）は決まっているが **アイデンティティ感が薄い**
- Twitter / Facebook タイムラインに流れた時に **スクロール手を止めさせる力がない**
- 動物詳細の OGP も絵文字頼みで、保護動物の「顔」が見えない

### 既存の配色 (Tailwind 変数として使われている)

- プライマリ: 暖色系オレンジ (`#9a3412`, `#7c2d12`, `#fff7ed`, `#ffedd5`, `#fed7aa`, `#fb923c`)
- 文字: `#7c2d12` 系の濃いブラウン
- フォント: Hiragino Sans / Yu Gothic（日本語）

## やってほしいこと

上記 3 つの `opengraph-image.tsx` を **`next/og` の `ImageResponse` で生成可能な範囲で** リブランディングしてください。重要なのは以下:

### 必須要件

1. **`next/og` の制約を守る**:
   - `<img>` は base64 / 外部 URL（HTTPS）のみ。SVG コード（path/circle/rect 等の primitive）はインライン埋め込み可
   - フォントは Google Fonts などから fetch して埋め込み可（既存は OS フォント依存で日本語が崩れる懸念あり）
   - 出力サイズ: 1200×630 (固定)

2. **ブランド感を強化**:
   - 犬・猫のシルエット or ピクトグラム（SVG）を中央〜余白に配置
   - メッセージ（「全国の保護動物を一つに」「殺処分ゼロへ」）を **主役** に
   - 既存のオレンジ系配色は維持（信頼感のある暖かい印象）

3. **3 ファイルで一貫性**: トップ・stats・動物詳細で共通のビジュアル言語（同じシルエット集、同じフォント、同じレイアウトグリッド）

4. **動物詳細 OGP は「カード型」に**:
   - 種別 (犬/猫) のシルエットを大きく
   - 性別アイコン (♂/♀)、都道府県、カテゴリ (譲渡対象/迷子/収容中) をバッジ表示
   - 「この子の里親になる」CTA 風メッセージ

5. **stats OGP は数字を主役に**:
   - 大きな数字 (累計頭数) で「規模感」を訴求
   - 都道府県・サイト数を補足

6. **アクセシビリティ**: `alt` テキストも `export const alt` で適切に更新

### やってはいけないこと

- 写真素材は使わない (`next/og` で外部画像 fetch すると遅い・失敗する)
- 過度に派手な配色変更（既存のオレンジ系から大きく離れない）
- 日本語フォントの埋め込みを忘れない（OS フォントだとサーバ側で文字化けする可能性）

### 成果物

- 3 つの `opengraph-image.tsx` のリブランド版コード
- 各ファイルのプレビュー画像 (1200×630 PNG) を1枚ずつ添付
- 既存テスト (`frontend/components/animals/PetSchema.test.tsx` 等) を壊さないこと
- `npx tsc --noEmit` と `npm run lint` がクリーンであること

## ゴール

Twitter / Bluesky / Facebook で oneco の URL がシェアされた時に **「何これ気になる」** とクリックしたくなる OGP。SNS 集客の入口として機能するレベルに引き上げてほしい。

---

## 参考: 既存 3 ファイルの実コード

### 1. `frontend/app/opengraph-image.tsx` (トップページ用)

```tsx
import { ImageResponse } from 'next/og';

export const alt = 'oneco - 全国の保護動物情報';
export const size = { width: 1200, height: 630 };
export const contentType = 'image/png';

export default function OpengraphImage() {
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
        }}
      >
        <div
          style={{
            fontSize: 96,
            fontWeight: 700,
            color: '#9a3412',
            letterSpacing: '-0.02em',
            marginBottom: 32,
          }}
        >
          oneco
        </div>
        <div
          style={{
            fontSize: 36,
            color: '#7c2d12',
            fontWeight: 500,
            textAlign: 'center',
            maxWidth: 900,
          }}>
          全国の保護動物を一つに
        </div>
        <div
          style={{
            fontSize: 22,
            color: '#9a3412',
            marginTop: 24,
            opacity: 0.8,
          }}
        >
          自治体の保護動物情報を統一プラットフォームで
        </div>
        <div
          style={{
            display: 'flex',
            gap: 12,
            marginTop: 48,
            fontSize: 32,
          }}
        >
          <span>🐕</span>
          <span>🐈</span>
        </div>
      </div>
    ),
    size,
  );
}
```

### 2. `frontend/app/stats/opengraph-image.tsx` (実績ページ用・動的)

```tsx
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
```

### 3. `frontend/app/animals/[id]/opengraph-image.tsx` (動物詳細用・動的)

```tsx
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
```

---

## 補足: 動作確認方法

実装後、ローカルで以下を実行してプレビュー画像を確認できます:

```bash
cd frontend
npm run dev
# 別ターミナルで:
open http://localhost:3000/opengraph-image
open http://localhost:3000/stats/opengraph-image
open http://localhost:3000/animals/1/opengraph-image
```

本番後の確認:

```bash
# SNS シェアの見た目チェック
open "https://cards-dev.twitter.com/validator?url=https%3A%2F%2Ffrontend-psi-ten-73.vercel.app%2F"
# Facebook 側
open "https://developers.facebook.com/tools/debug/?q=https%3A%2F%2Ffrontend-psi-ten-73.vercel.app%2F"
```
