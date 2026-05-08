import { promises as fs } from 'fs';
import path from 'path';
import type { Topology } from 'topojson-specification';
import { bucketColor, projectPrefectures } from '@/lib/japan-map';

interface JapanMapProps {
  /** 都道府県名 → 件数 */
  countsByPrefecture: Record<string, number>;
}

async function loadTopology(): Promise<Topology> {
  const filePath = path.join(process.cwd(), 'public', 'maps', 'japan.topojson');
  const raw = await fs.readFile(filePath, 'utf-8');
  return JSON.parse(raw) as Topology;
}

export async function JapanMap({ countsByPrefecture }: JapanMapProps) {
  const topology = await loadTopology();
  const { width, height, geometries } = projectPrefectures(topology);

  const max = Math.max(0, ...Object.values(countsByPrefecture));
  const totalAnimals = Object.values(countsByPrefecture).reduce(
    (sum, n) => sum + n,
    0,
  );
  const totalPrefectures = Object.values(countsByPrefecture).filter(
    (n) => n > 0,
  ).length;

  return (
    <section
      aria-labelledby="japan-map-heading"
      className="bg-white rounded-lg shadow-md p-6 space-y-4"
    >
      <div className="flex items-baseline justify-between flex-wrap gap-2">
        <h2
          id="japan-map-heading"
          className="text-lg font-semibold text-[var(--color-text-primary)]"
        >
          全国の保護動物マップ
        </h2>
        <p className="text-sm text-[var(--color-text-secondary)]">
          全国 <span className="font-semibold">{totalAnimals}</span>件 /{' '}
          <span className="font-semibold">{totalPrefectures}</span>
          都道府県でデータ収集中
        </p>
      </div>

      <div className="flex flex-col gap-4 lg:flex-row lg:items-start">
        <div className="flex-1 min-w-0">
          <svg
            viewBox={`0 0 ${width} ${height}`}
            className="w-full h-auto max-h-[70vh]"
            role="img"
            aria-label="日本地図 — クリックで都道府県別の一覧へ"
          >
            {geometries.map((g) => {
              const count = countsByPrefecture[g.prefecture] ?? 0;
              const fill = bucketColor(count, max);
              const href = `/?prefecture=${encodeURIComponent(g.prefecture)}`;
              const label = `${g.prefecture}: ${count}件`;
              return (
                <a key={g.prefecture} href={href} aria-label={label}>
                  <title>{label}</title>
                  <path
                    d={g.d}
                    fill={fill}
                    stroke="#9ca3af"
                    strokeWidth={0.5}
                    className="transition-opacity hover:opacity-80"
                  />
                </a>
              );
            })}
          </svg>
        </div>

        <aside className="lg:w-48 lg:shrink-0 space-y-2">
          <h3 className="text-sm font-semibold text-[var(--color-text-secondary)]">
            件数の凡例
          </h3>
          <ul className="text-xs space-y-1">
            {[
              { label: 'データなし', color: '#f3f4f6' },
              { label: '少ない', color: '#fed7aa' },
              { label: '', color: '#fdba74' },
              { label: '中程度', color: '#fb923c' },
              { label: '', color: '#f97316' },
              { label: '多い', color: '#ea580c' },
            ].map((item, i) => (
              <li key={i} className="flex items-center gap-2">
                <span
                  className="inline-block w-4 h-4 border border-gray-300"
                  style={{ backgroundColor: item.color }}
                  aria-hidden="true"
                />
                <span>{item.label}</span>
              </li>
            ))}
          </ul>
          <p className="text-xs text-[var(--color-text-secondary)] pt-2">
            地図をクリックすると、その県で絞り込まれた一覧へ移動します。
          </p>
        </aside>
      </div>
    </section>
  );
}
