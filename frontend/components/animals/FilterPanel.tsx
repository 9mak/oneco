/**
 * FilterPanel Component
 * フィルタUI提供、フィルタ状態管理、URLクエリパラメータ同期
 */

'use client';

import { FilterState } from '@/types/animal';
import { useState, useEffect } from 'react';

interface FilterPanelProps {
  filters: FilterState;
  onFilterChange: (key: keyof FilterState, value: string | undefined) => void;
  onClearFilters: () => void;
  resultCount: number;
}

/** タブの定義 */
type TabValue = 'sheltered' | 'adoption';

const TABS: { value: TabValue; label: string }[] = [
  { value: 'sheltered', label: '収容中の子を探す' },
  { value: 'adoption', label: '家族を迎える' },
];

/**
 * フィルタのcategoryからアクティブタブを導出する。
 * "lost" と "sheltered" はどちらも「収容中」タブ扱い。
 */
function categoryToTab(category: FilterState['category']): TabValue | null {
  if (category === 'adoption') return 'adoption';
  if (category === 'lost' || category === 'sheltered') return 'sheltered';
  return null;
}

export function FilterPanel({
  filters,
  onFilterChange,
  onClearFilters,
  resultCount,
}: FilterPanelProps) {
  const [locationInput, setLocationInput] = useState(filters.location || '');

  // Debounce地域フィルタ (500ms)
  useEffect(() => {
    const timer = setTimeout(() => {
      if (locationInput !== filters.location) {
        onFilterChange('location', locationInput || undefined);
      }
    }, 500);

    return () => clearTimeout(timer);
  }, [locationInput, filters.location, onFilterChange]);

  // フィルタが適用されているかチェック
  const hasActiveFilters =
    filters.category || filters.species || filters.sex || filters.location;

  const activeTab = categoryToTab(filters.category);

  const handleTabClick = (tab: TabValue) => {
    if (activeTab === tab) {
      // 同じタブを再クリック → タブ解除（全件表示）
      onFilterChange('category', undefined);
    } else {
      onFilterChange('category', tab);
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-md overflow-hidden">
      {/* タブ */}
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

      {/* フィルタエリア */}
      <div className="p-6 space-y-4">
        <div className="flex items-center justify-between">
          <span className="text-sm text-[var(--color-text-secondary)]">
            {resultCount}件の動物
          </span>
        </div>

        {/* フィルタフォーム */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* 種別フィルタ */}
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
              onChange={(e) =>
                onFilterChange('species', e.target.value || undefined)
              }
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-[var(--color-focus-ring)] min-h-[44px]"
            >
              <option value="">すべて</option>
              <option value="犬">犬</option>
              <option value="猫">猫</option>
            </select>
          </div>

          {/* 性別フィルタ */}
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
              onChange={(e) => onFilterChange('sex', e.target.value || undefined)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-[var(--color-focus-ring)] min-h-[44px]"
            >
              <option value="">すべて</option>
              <option value="男の子">男の子</option>
              <option value="女の子">女の子</option>
              <option value="不明">不明</option>
            </select>
          </div>

          {/* 地域フィルタ */}
          <div>
            <label
              htmlFor="location-filter"
              className="block text-sm font-medium text-[var(--color-text-primary)] mb-2"
            >
              地域
            </label>
            <input
              id="location-filter"
              type="text"
              value={locationInput}
              onChange={(e) => setLocationInput(e.target.value)}
              placeholder="都道府県名で検索"
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-[var(--color-focus-ring)] min-h-[44px]"
            />
          </div>
        </div>

        {/* フィルタクリアボタン */}
        {hasActiveFilters && (
          <div className="flex justify-end">
            <button
              onClick={onClearFilters}
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
