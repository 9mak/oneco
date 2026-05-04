'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { FilterState } from '@/types/animal';

const PREFECTURES = [
  '北海道', '青森県', '岩手県', '宮城県', '秋田県', '山形県', '福島県',
  '茨城県', '栃木県', '群馬県', '埼玉県', '千葉県', '東京都', '神奈川県',
  '新潟県', '富山県', '石川県', '福井県', '山梨県', '長野県', '岐阜県',
  '静岡県', '愛知県', '三重県', '滋賀県', '京都府', '大阪府', '兵庫県',
  '奈良県', '和歌山県', '鳥取県', '島根県', '岡山県', '広島県', '山口県',
  '徳島県', '香川県', '愛媛県', '高知県', '福岡県', '佐賀県', '長崎県',
  '熊本県', '大分県', '宮崎県', '鹿児島県', '沖縄県',
];

interface FilterPanelProps {
  filters: FilterState;
  resultCount: number;
}

type TabValue = 'sheltered' | 'adoption';

const TABS: { value: TabValue; label: string }[] = [
  { value: 'sheltered', label: '収容中の子を探す' },
  { value: 'adoption', label: '家族を迎える' },
];

function categoryToTab(category: FilterState['category']): TabValue | null {
  if (category === 'adoption') return 'adoption';
  if (category === 'lost' || category === 'sheltered') return 'sheltered';
  return null;
}

export function FilterPanel({ filters, resultCount }: FilterPanelProps) {
  const router = useRouter();
  const searchParams = useSearchParams();

  const updateParam = (key: keyof FilterState, value: string | undefined) => {
    const newParams = new URLSearchParams(searchParams.toString());
    if (value) {
      newParams.set(key, value);
    } else {
      newParams.delete(key);
    }
    const qs = newParams.toString();
    router.replace(qs ? `?${qs}` : '/', { scroll: false });
  };

  const clearAll = () => {
    router.replace('/', { scroll: false });
  };

  const hasActiveFilters =
    filters.category ||
    filters.species ||
    filters.sex ||
    filters.location ||
    filters.prefecture;

  const activeTab = categoryToTab(filters.category);

  const handleTabClick = (tab: TabValue) => {
    if (activeTab === tab) {
      updateParam('category', undefined);
    } else {
      updateParam('category', tab);
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-md overflow-hidden">
      <div
        className="flex border-b border-gray-200"
        role="tablist"
        aria-label="カテゴリ選択"
      >
        {TABS.map((tab) => {
          const isActive = activeTab === tab.value;
          return (
            <button
              key={tab.value}
              role="tab"
              aria-selected={isActive}
              onClick={() => handleTabClick(tab.value)}
              className={[
                'flex-1 px-6 py-3 text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-inset focus:ring-[var(--color-focus-ring)] min-h-[44px]',
                isActive
                  ? 'border-b-2 border-[var(--color-primary-500)] text-[var(--color-primary-500)] bg-white'
                  : 'text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-gray-50',
              ].join(' ')}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      <div className="p-6 space-y-4">
        <div className="flex items-center justify-between">
          <span className="text-sm text-[var(--color-text-secondary)]">
            {resultCount}件の動物
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label
              htmlFor="species-filter"
              className="block text-sm font-medium text-[var(--color-text-primary)] mb-2"
            >
              種別
            </label>
            <select
              id="species-filter"
              value={filters.species || ''}
              onChange={(e) => updateParam('species', e.target.value || undefined)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-[var(--color-focus-ring)] min-h-[44px]"
            >
              <option value="">すべて</option>
              <option value="犬">犬</option>
              <option value="猫">猫</option>
            </select>
          </div>

          <div>
            <label
              htmlFor="sex-filter"
              className="block text-sm font-medium text-[var(--color-text-primary)] mb-2"
            >
              性別
            </label>
            <select
              id="sex-filter"
              value={filters.sex || ''}
              onChange={(e) => updateParam('sex', e.target.value || undefined)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-[var(--color-focus-ring)] min-h-[44px]"
            >
              <option value="">すべて</option>
              <option value="男の子">男の子</option>
              <option value="女の子">女の子</option>
              <option value="不明">不明</option>
            </select>
          </div>

          <div>
            <label
              htmlFor="prefecture-filter"
              className="block text-sm font-medium text-[var(--color-text-primary)] mb-2"
            >
              地域
            </label>
            <select
              id="prefecture-filter"
              value={filters.prefecture || ''}
              onChange={(e) => updateParam('prefecture', e.target.value || undefined)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-[var(--color-focus-ring)] min-h-[44px]"
            >
              <option value="">すべて</option>
              {PREFECTURES.map((pref) => (
                <option key={pref} value={pref}>{pref}</option>
              ))}
            </select>
          </div>
        </div>

        {hasActiveFilters && (
          <div className="flex justify-end">
            <button
              onClick={clearAll}
              className="px-4 py-2 text-sm font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-primary-700)] transition-colors focus:outline-none focus:ring-2 focus:ring-[var(--color-focus-ring)] focus:ring-offset-2 min-h-[44px]"
              aria-label="フィルタをクリア"
            >
              フィルタをクリア
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
