import Link from 'next/link';

import { computeQuantileBins, getBinIndex } from '@/lib/heatmap-bins';
import {
  CELL_SIZE,
  GRID_COLS,
  GRID_ROWS,
  PREFECTURE_COORDS,
} from '@/lib/prefecture-grid-coords';

interface JapanSymbolMapProps {
  countsByPrefecture: Record<string, number>;
}

/**
 * 軽量 SVG ベースの日本シンボル地図
 *
 * 外部依存ゼロ（d3-geo / TopoJSON 不要）で 47 都道府県を簡略化された四角タイルで配置。
 * 件数のヒートマップ濃度 + a11y (キーボードフォーカス、aria-label、SR 等価 table) を備える。
 */

const BIN_COLORS: { fill: string; stroke: string; text: string }[] = [
  // 0 = データなし
  { fill: '#f3f4f6', stroke: '#d1d5db', text: '#374151' },
  // 1 = 最少
  { fill: '#fff7ed', stroke: '#fed7aa', text: '#7c2d12' },
  // 2
  { fill: '#ffedd5', stroke: '#fdba74', text: '#7c2d12' },
  // 3
  { fill: '#fed7aa', stroke: '#fb923c', text: '#431407' },
  // 4
  { fill: '#fdba74', stroke: '#f97316', text: '#431407' },
  // 5 = 最多
  { fill: '#fb923c', stroke: '#ea580c', text: '#ffffff' },
];

function getColors(bin: number) {
  return BIN_COLORS[bin] ?? BIN_COLORS[0];
}

export function JapanSymbolMap({ countsByPrefecture }: JapanSymbolMapProps) {
  const totalAnimals = Object.values(countsByPrefecture).reduce(
    (sum, n) => sum + n,
    0,
  );
  const nonZeroCount = Object.values(countsByPrefecture).filter((n) => n > 0).length;
  const bins = computeQuantileBins(Object.values(countsByPrefecture), 5);

  const viewBoxWidth = GRID_COLS * CELL_SIZE;
  const viewBoxHeight = GRID_ROWS * CELL_SIZE;
  const padding = 4;
  const tileSize = CELL_SIZE - padding * 2;
  const labelTitle = `47 都道府県のうち ${nonZeroCount} 県で計 ${totalAnimals} 件の保護動物を地図表示`;

  return (
    <section
      className="bg-white rounded-lg shadow-md p-6 space-y-4"
      aria-labelledby="japan-symbol-map-heading"
    >
      <div className="flex items-baseline justify-between flex-wrap gap-2">
        <h2
          id="japan-symbol-map-heading"
          className="text-lg font-semibold text-[var(--color-text-primary)]"
        >
          全国マップ（簡略表示）
        </h2>
        <p className="text-sm text-[var(--color-text-secondary)]">
          全国 <span className="font-semibold">{totalAnimals}</span>件 /{' '}
          <span className="font-semibold">{nonZeroCount}</span>都道府県
        </p>
      </div>

      <div className="w-full overflow-x-auto">
        <svg
          viewBox={`0 0 ${viewBoxWidth} ${viewBoxHeight}`}
          role="img"
          aria-label={labelTitle}
          className="w-full max-w-3xl mx-auto h-auto"
          xmlns="http://www.w3.org/2000/svg"
        >
          <title>{labelTitle}</title>
          {Object.entries(PREFECTURE_COORDS).map(([pref, { col, row }]) => {
            const count = countsByPrefecture[pref] ?? 0;
            const bin = getBinIndex(count, bins);
            const colors = getColors(bin);
            const x = col * CELL_SIZE + padding;
            const y = row * CELL_SIZE + padding;
            const shortLabel = pref.replace(/[県府都道]$/, '');
            const ariaLabel = `${pref}: ${count}件${count > 0 ? `（ヒートマップ濃度 ${bin}/5）` : '（データなし）'}`;
            const tile = (
              <g key={pref}>
                <rect
                  x={x}
                  y={y}
                  width={tileSize}
                  height={tileSize}
                  rx={4}
                  ry={4}
                  fill={colors.fill}
                  stroke={colors.stroke}
                  strokeWidth={1.5}
                />
                <text
                  x={x + tileSize / 2}
                  y={y + tileSize / 2 - 6}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  fontSize={12}
                  fontWeight={500}
                  fill={colors.text}
                  pointerEvents="none"
                >
                  {shortLabel}
                </text>
                <text
                  x={x + tileSize / 2}
                  y={y + tileSize / 2 + 12}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  fontSize={11}
                  fontWeight={700}
                  fill={colors.text}
                  pointerEvents="none"
                >
                  {count}
                </text>
              </g>
            );
            // 件数 0 はクリック無効、focus 不可。SR には data table で全件提供。
            if (count === 0) {
              return (
                <g key={pref} aria-label={ariaLabel} role="img">
                  {tile}
                </g>
              );
            }
            return (
              <Link
                key={pref}
                href={`/?prefecture=${encodeURIComponent(pref)}`}
                aria-label={ariaLabel}
                className="cursor-pointer focus:outline focus:outline-2 focus:outline-orange-700"
              >
                {tile}
              </Link>
            );
          })}
        </svg>
      </div>

      {/* SR 向け等価表現: 件数が SVG だけでは伝わらないので table も提供 */}
      <details className="text-sm text-[var(--color-text-secondary)]">
        <summary className="cursor-pointer font-medium">
          表で見る（スクリーンリーダー対応）
        </summary>
        <table className="mt-2 w-full text-sm">
          <caption className="sr-only">{labelTitle}</caption>
          <thead className="bg-gray-50">
            <tr>
              <th className="px-3 py-2 text-left font-medium">都道府県</th>
              <th className="px-3 py-2 text-right font-medium">件数</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(PREFECTURE_COORDS).map(([pref]) => (
              <tr key={pref} className="border-t border-gray-200">
                <td className="px-3 py-2">{pref}</td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {countsByPrefecture[pref] ?? 0}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </section>
  );
}
