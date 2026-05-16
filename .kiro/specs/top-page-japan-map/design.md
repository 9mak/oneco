# Technical Design Document: Top Page Japan Map

## 1. Overview

トップページに 47 都道府県のヒートマップ付きインタラクティブ日本地図を新設し、保護動物の地域分布を視覚化する。既存の地方別グリッドは併存させて progressive enhancement とする。

主要な設計判断：

- **地図データ**: 公開 GeoJSON / TopoJSON を使用、ライブラリは d3-geo（軽量、SSR 互換、TypeScript 完備）
- **描画**: SVG（Canvas より a11y 容易、Tailwind での装飾互換）
- **クライアント JS 最小化**: 初期 HTML は完全静的、件数だけ Server Component で fetch、インタラクション部分のみ動的 import
- **API**: 既存 `/api/animals` に `by_prefecture=true` クエリで集計を返す形に拡張（新規エンドポイント不要）

## 2. Architecture Pattern & Boundary Map

```
┌────────────────────────────────────────────────────────────────┐
│                    Next.js 16 App Router                        │
│                                                                 │
│  app/page.tsx (RSC, SSG-friendly)                              │
│   ├─ <Suspense>                                                │
│   │    └─ <JapanMapServerWrapper /> (Server Component)         │
│   │         ├─ fetch('/api/animals?by_prefecture=true')        │
│   │         └─ renders <JapanMap data={...} /> (Client lazy)   │
│   └─ <PrefectureGrid /> (existing, fallback if JS off)         │
│                                                                 │
│  components/map/                                               │
│   ├─ JapanMap.tsx (Client, dynamic import)                     │
│   ├─ PrefecturePath.tsx (個別 path + a11y attrs)               │
│   ├─ MapLegend.tsx                                             │
│   ├─ MapTooltip.tsx                                            │
│   └─ data/japan-prefectures.topojson (~50KB gzipped)           │
└──────────────────────────┬─────────────────────────────────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │  FastAPI: /api/animals  │
              │   ?by_prefecture=true   │
              │   → 47 件の集計を返却   │
              └────────────────────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │  PostgreSQL (animals)   │
              │  GROUP BY prefecture    │
              └────────────────────────┘
```

### 境界判断

- **API は既存拡張**: 新規エンドポイント `/api/animals/by-prefecture` を作るより、既存に `by_prefecture=true` を追加した方が API 表面積が増えない
- **TopoJSON を frontend バンドルに含める**: 都道府県データは静的、CDN 経由よりバンドルしてキャッシュ最大化（gzip 後 50KB）

## 3. Technology Stack & Alignment

| 層 | 採用技術 | 根拠 |
|---|---|---|
| 地図ライブラリ | `d3-geo` + 自前 SVG レンダ | React-Japan-Map は古い、@svg-japan/react は依存重い |
| TopoJSON | `topojson-client` | d3-geo と組合せ、世界標準 |
| データソース | `mb-yamamoto/japan-topojson`（軽量版） | 都道府県境界、CC0、~50KB |
| Tooltip | Radix UI Popover or 自前 | Radix を既存採用してなければ自前で SVG `<title>` + visual tooltip |
| 動的 import | `next/dynamic` `{ ssr: false }` | インタラクション部分のみ Client、初期 HTML は静的 |

## 4. Components & Interface Contracts

### 4.1 Server Component

**`app/page.tsx`**

```tsx
export default async function HomePage() {
  const data = await fetchPrefectureCounts(); // Server-side
  return (
    <>
      <h1>全国の保護動物</h1>
      <JapanMapServerWrapper data={data} />
      <PrefectureGrid data={data} /> {/* fallback / 併存 */}
    </>
  );
}
```

**`components/map/JapanMapServerWrapper.tsx`**

```tsx
import dynamic from "next/dynamic";

const JapanMap = dynamic(() => import("./JapanMap"), {
  ssr: true, // 初期 HTML に SVG を含める
  loading: () => <MapSkeleton />,
});

export function JapanMapServerWrapper({ data }: { data: PrefectureCount[] }) {
  return <JapanMap data={data} />;
}
```

### 4.2 Client Component (Interactive)

**`components/map/JapanMap.tsx`**

```tsx
"use client";

import * as topojson from "topojson-client";
import { geoMercator, geoPath } from "d3-geo";
import japanData from "./data/japan-prefectures.topojson.json";

interface PrefectureCount {
  prefecture: string; // "東京都" 等
  count: number;
}

interface Props {
  data: PrefectureCount[];
}

export function JapanMap({ data }: Props) {
  const features = useMemo(
    () => topojson.feature(japanData, japanData.objects.prefectures),
    []
  );
  const countByPref = useMemo(
    () => new Map(data.map((d) => [d.prefecture, d.count])),
    [data]
  );
  const bins = useMemo(() => computeQuantileBins(data, 5), [data]);

  return (
    <svg viewBox="0 0 800 800" role="img" aria-label={ariaLabel(data)}>
      <title>全国保護動物分布マップ</title>
      <desc>47 都道府県のうち {nonZero(data)} 県で保護動物がいます</desc>
      {features.features.map((f) => (
        <PrefecturePath
          key={f.properties.name}
          feature={f}
          count={countByPref.get(f.properties.name) ?? 0}
          colorBin={getBin(countByPref.get(f.properties.name), bins)}
          onSelect={navigateToList}
        />
      ))}
      <MapLegend bins={bins} />
    </svg>
  );
}
```

### 4.3 PrefecturePath（a11y フォーカス対応）

```tsx
interface PrefecturePathProps {
  feature: GeoFeature;
  count: number;
  colorBin: number; // 0-4
  onSelect: (prefecture: string) => void;
}

export function PrefecturePath({ feature, count, colorBin, onSelect }: PrefecturePathProps) {
  const isClickable = count > 0;
  return (
    <path
      d={pathGenerator(feature)}
      fill={isClickable ? colors[colorBin] : "var(--color-neutral-200)"}
      stroke="var(--color-neutral-400)"
      strokeWidth={0.5}
      tabIndex={isClickable ? 0 : -1}
      role={isClickable ? "button" : undefined}
      aria-label={`${feature.properties.name}: ${count}件`}
      onClick={isClickable ? () => onSelect(feature.properties.name) : undefined}
      onKeyDown={(e) => {
        if (isClickable && (e.key === "Enter" || e.key === " ")) onSelect(feature.properties.name);
      }}
      className={isClickable ? "cursor-pointer focus:outline focus:outline-2 focus:outline-primary-700" : "cursor-not-allowed"}
    />
  );
}
```

### 4.4 Backend 拡張

**`src/data_collector/infrastructure/api/routes/animals.py`** (既存ファイル拡張):

```python
class PrefectureCount(BaseModel):
    prefecture: str
    count: int

@router.get("/animals", response_model=AnimalsResponse | list[PrefectureCount])
async def list_animals(
    by_prefecture: bool = False,
    ...
):
    if by_prefecture:
        rows = await db.fetch(
            "SELECT prefecture, COUNT(*) FROM animals "
            "WHERE listing_status = 'active' "
            "GROUP BY prefecture"
        )
        return [PrefectureCount(prefecture=r["prefecture"], count=r["count"]) for r in rows]
    # 既存ロジック
    ...
```

## 5. Data Model

新規テーブル不要。既存 `animals` テーブルへの GROUP BY のみ。

## 6. Performance Strategy

- **TopoJSON サイズ**: 軽量版（簡略化 0.01 度）で gzipped 50KB。Vercel の自動 gzip + immutable cache で初回後はキャッシュ
- **動的 import**: 初期 HTML には SVG 含めるが、インタラクション JS は遅延ロード（`ssr: true` + `loading="lazy"` の組合せは React 19 で対応）
- **LCP 対策**: 地図 SVG は `<picture>` ではなくインライン SVG として初期 HTML に含めて FCP に含める
- **CLS 対策**: SVG コンテナに固定 aspect-ratio (1:1) を CSS で指定

## 7. Accessibility

| 要件 | 実装 |
|---|---|
| Screen reader 等価 | `<svg role="img" aria-label="...">` + 隠し `<table>` を `aria-describedby` |
| Keyboard nav | `tabIndex={0}` + Enter/Space ハンドラ |
| Focus indicator | Tailwind `focus:outline focus:outline-2 focus:outline-primary-700` (4.5:1 確保) |
| Color contrast | quantile bin の各色を `primary-200`〜`primary-900` で AA 確保 |
| カウント 0 県 | `tabIndex={-1}`, `cursor-not-allowed`, クリック無効 |

## 8. Responsive Design

| ブレークポイント | レイアウト |
|---|---|
| `lg` (≥1024px) | SVG 幅 800px, 凡例右下 |
| `md` (≥768px) | SVG 幅 600px, 凡例下部 |
| `sm` (<768px) | SVG 幅 100%, 凡例下部、tooltip タッチ対応 |
| `<640px` フォールバック | リスト + 凡例 UI（既存 PrefectureGrid 再利用） |

## 9. SEO & Sharing

- **Server-side fetch**: 初期 HTML に件数文字列を埋め込み（クローラ向け）
- **OG image**: `app/opengraph-image.tsx` で動的に「全国 47 都道府県、X 件の保護動物」を画像生成
- **Lighthouse target**: Performance ≥80, A11y =100

## 10. Testing Strategy

| 層 | フレームワーク | カバレッジ |
|---|---|---|
| ユニット | vitest + @testing-library/react | JapanMap, PrefecturePath, MapLegend |
| 視覚回帰 | Playwright screenshots | 地図全体、各ブレークポイント |
| E2E インタラクション | Playwright | hover / click / keyboard nav |
| a11y | @axe-core/playwright | 0 violation (WCAG AA) |
| Performance | Lighthouse CI | Performance ≥80, A11y =100 |
| API | pytest | `/api/animals?by_prefecture=true` の集計正しさ |

## 11. Risks & Mitigations

| リスク | 影響 | 対策 |
|---|---|---|
| TopoJSON サイズが LCP を悪化 | 初回読み込み遅延 | 軽量版 + gzip + immutable cache |
| `d3-geo` が SSR で hydration mismatch | 画面ちらつき | サーバ・クライアントで同一 path 生成、`useMemo` でメモ化 |
| 地図表示で a11y 退行 | WCAG 退行 | E2E a11y を必須化、tabIndex を片っ端から検証 |
| 県名の API 表記揺れ | マッピング失敗 | 県名は ISO 3166-2:JP コードで正規化、`prefecture_name_to_code` ヘルパ追加 |
| モバイルでの操作性 | UX 低下 | 44x44 タッチターゲット最低保証、長押しで tooltip |

## 12. Requirements Traceability

| Req | 対応コンポーネント |
|---|---|
| 1.1–1.6 | `JapanMap`, `JapanMapServerWrapper`, dynamic import, LCP/CLS 設計 |
| 2.1–2.6 | `computeQuantileBins`, `MapLegend`, `/api/animals?by_prefecture=true` |
| 3.1–3.5 | `PrefecturePath` (onClick, onHover, tooltip, cursor) |
| 4.1–4.6 | `PrefecturePath` (tabIndex, aria-label, keyboard handler), 等価 data table |
| 5.1–5.5 | レスポンシブブレークポイント, タッチターゲット, フォールバック UI |
| 6.1–6.4 | View toggle, localStorage 永続化 |
| 7.1–7.5 | Server Component fetch, OG image, Lighthouse, progressive enhancement |
| 8.1–8.4 | vitest/Playwright/a11y/エラー時フォールバック |
