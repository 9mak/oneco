import Link from 'next/link';

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

function PrefectureCell({ pref, count }: { pref: string; count: number }) {
  const hasData = count > 0;
  const href = `/?prefecture=${encodeURIComponent(pref)}`;
  const label = hasData ? `${pref}: ${count}件` : `${pref}: データなし`;

  return (
    <Link
      href={href}
      aria-label={label}
      className={[
        'flex flex-col items-center justify-center rounded-md py-2 px-1 text-xs transition-colors min-h-[60px]',
        hasData
          ? 'bg-orange-50 hover:bg-orange-100 text-orange-900 border border-orange-200'
          : 'bg-gray-50 hover:bg-gray-100 text-gray-400 border border-gray-100',
      ].join(' ')}
    >
      <span className="font-medium">{pref}</span>
      <span
        className={[
          'mt-1 px-2 py-0.5 rounded-full text-[10px] font-bold',
          hasData ? 'bg-orange-500 text-white' : 'bg-gray-300 text-white',
        ].join(' ')}
      >
        {count}
      </span>
    </Link>
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
                {region.prefectures.map((pref) => (
                  <PrefectureCell
                    key={pref}
                    pref={pref}
                    count={countsByPrefecture[pref] || 0}
                  />
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
