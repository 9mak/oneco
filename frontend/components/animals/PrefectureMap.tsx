import Link from 'next/link';

import { computeQuantileBins, getBinIndex } from '@/lib/heatmap-bins';

interface PrefectureMapProps {
  /** 都道府県名 → 件数 */
  countsByPrefecture: Record<string, number>;
}

/**
 * 地方別グリッドで日本全国の保護動物分布を可視化
 *
 * SVG マップは将来対応。現状は地方ごとに 47 都道府県を区分けし、
 * 件数バッジ + クリックでフィルター遷移する形式。
 */
const REGIONS: { name: string; prefectures: string[] }[] = [
  { name: '北海道', prefectures: ['北海道'] },
  {
    name: '東北',
    prefectures: ['青森県', '岩手県', '宮城県', '秋田県', '山形県', '福島県'],
  },
  {
    name: '関東',
    prefectures: [
      '茨城県',
      '栃木県',
      '群馬県',
      '埼玉県',
      '千葉県',
      '東京都',
      '神奈川県',
    ],
  },
  {
    name: '中部',
    prefectures: [
      '新潟県',
      '富山県',
      '石川県',
      '福井県',
      '山梨県',
      '長野県',
      '岐阜県',
      '静岡県',
      '愛知県',
    ],
  },
  {
    name: '近畿',
    prefectures: [
      '三重県',
      '滋賀県',
      '京都府',
      '大阪府',
      '兵庫県',
      '奈良県',
      '和歌山県',
    ],
  },
  {
    name: '中国',
    prefectures: ['鳥取県', '島根県', '岡山県', '広島県', '山口県'],
  },
  { name: '四国', prefectures: ['徳島県', '香川県', '愛媛県', '高知県'] },
  {
    name: '九州・沖縄',
    prefectures: [
      '福岡県',
      '佐賀県',
      '長崎県',
      '熊本県',
      '大分県',
      '宮崎県',
      '鹿児島県',
      '沖縄県',
    ],
  },
];

// ヒートマップ濃度: bin 0 = データなし, 1〜5 = quantile bin (薄い → 濃い)
// 各 class は WCAG AA (4.5:1) を満たすため orange-X 系の濃淡と text の組合せを慎重に選定。
const BIN_CLASSES: { card: string; badge: string }[] = [
  // 0 = データなし
  {
    card: 'bg-gray-50 text-gray-700 border-gray-100',
    badge: 'bg-gray-500 text-white',
  },
  // 1 = 最も少ない bin
  {
    card: 'bg-orange-50 hover:bg-orange-100 text-orange-900 border-orange-200',
    badge: 'bg-orange-500 text-white',
  },
  // 2
  {
    card: 'bg-orange-100 hover:bg-orange-200 text-orange-900 border-orange-300',
    badge: 'bg-orange-600 text-white',
  },
  // 3
  {
    card: 'bg-orange-200 hover:bg-orange-300 text-orange-950 border-orange-400',
    badge: 'bg-orange-700 text-white',
  },
  // 4
  {
    card: 'bg-orange-300 hover:bg-orange-400 text-orange-950 border-orange-500',
    badge: 'bg-orange-800 text-white',
  },
  // 5 = 最も多い bin
  {
    card: 'bg-orange-400 hover:bg-orange-500 text-orange-950 border-orange-600',
    badge: 'bg-orange-900 text-white',
  },
];

const BIN_COUNT = 5;

function PrefectureCell({
  pref,
  count,
  bin,
}: {
  pref: string;
  count: number;
  bin: number;
}) {
  const hasData = count > 0;
  const classes = BIN_CLASSES[bin] ?? BIN_CLASSES[0];
  const baseClass =
    'flex flex-col items-center justify-center rounded-md py-2 px-1 text-xs transition-colors min-h-[60px]';
  const innerNode = (
    <>
      <span className="font-medium">{pref}</span>
      <span
        className={`mt-1 px-2 py-0.5 rounded-full text-[10px] font-bold ${classes.badge}`}
      >
        {count}
      </span>
    </>
  );

  // データがない県はクリックしても結果が無いため、Link ではなく非インタラクティブな div で
  // 表示する。axe-core の nested-interactive 検出回避と UX 改善を兼ねる。
  if (!hasData) {
    return (
      <div
        aria-label={`${pref}: データなし`}
        className={`${baseClass} border ${classes.card}`}
      >
        {innerNode}
      </div>
    );
  }

  return (
    <Link
      href={`/?prefecture=${encodeURIComponent(pref)}`}
      aria-label={`${pref}: ${count}件 (ヒートマップ濃度 ${bin}/${BIN_COUNT})`}
      className={`${baseClass} border ${classes.card}`}
    >
      {innerNode}
    </Link>
  );
}

function MapLegend({ bins }: { bins: number[] }) {
  // bins[i] は bin i+1 の上限値。bin 1 = (0, bins[0]], bin 2 = (bins[0], bins[1]], ...
  const ranges: { label: string; bin: number }[] = [{ label: '0', bin: 0 }];
  if (bins.length === 0) {
    // データが薄い場合: 1 件以上は全て同じ bin として扱う
    ranges.push({ label: '1+', bin: 1 });
  } else {
    ranges.push({ label: `1–${bins[0]}`, bin: 1 });
    for (let i = 0; i < bins.length - 1; i++) {
      ranges.push({
        label: `${bins[i] + 1}–${bins[i + 1]}`,
        bin: i + 2,
      });
    }
    ranges.push({ label: `${bins[bins.length - 1] + 1}+`, bin: bins.length + 1 });
  }
  return (
    <div
      className="flex flex-wrap items-center gap-2 text-xs"
      role="group"
      aria-label="件数ヒートマップ凡例"
    >
      <span className="font-medium text-[var(--color-text-secondary)]">凡例:</span>
      {ranges.map((r) => {
        const c = BIN_CLASSES[r.bin] ?? BIN_CLASSES[0];
        return (
          <span
            key={`${r.bin}-${r.label}`}
            className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 ${c.card}`}
          >
            <span className={`inline-block h-2 w-2 rounded-full ${c.badge}`} aria-hidden />
            {r.label}
          </span>
        );
      })}
    </div>
  );
}

export function PrefectureMap({ countsByPrefecture }: PrefectureMapProps) {
  const totalAnimals = Object.values(countsByPrefecture).reduce(
    (sum, n) => sum + n,
    0,
  );
  const totalPrefectures = Object.values(countsByPrefecture).filter(
    (n) => n > 0,
  ).length;
  const bins = computeQuantileBins(Object.values(countsByPrefecture), BIN_COUNT);

  return (
    <section
      className="bg-white rounded-lg shadow-md p-6 space-y-4"
      aria-labelledby="prefecture-map-heading"
    >
      <div className="flex items-baseline justify-between flex-wrap gap-2">
        <h2
          id="prefecture-map-heading"
          className="text-lg font-semibold text-[var(--color-text-primary)]"
        >
          都道府県別の保護動物
        </h2>
        <p className="text-sm text-[var(--color-text-secondary)]">
          全国 <span className="font-semibold">{totalAnimals}</span>件 /{' '}
          <span className="font-semibold">{totalPrefectures}</span>
          都道府県でデータ収集中
        </p>
      </div>

      <MapLegend bins={bins} />

      <div className="space-y-4">
        {REGIONS.map((region) => {
          const regionTotal = region.prefectures.reduce(
            (sum, p) => sum + (countsByPrefecture[p] || 0),
            0,
          );
          return (
            <div key={region.name}>
              <h3 className="text-sm font-semibold text-[var(--color-text-secondary)] mb-2">
                {region.name}{' '}
                <span className="text-xs font-normal">({regionTotal}件)</span>
              </h3>
              <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 gap-2">
                {region.prefectures.map((pref) => {
                  const count = countsByPrefecture[pref] || 0;
                  return (
                    <PrefectureCell
                      key={pref}
                      pref={pref}
                      count={count}
                      bin={getBinIndex(count, bins)}
                    />
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
