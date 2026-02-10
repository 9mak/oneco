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

  return (
    <div className="bg-white p-6 rounded-lg shadow-md space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">
          絞り込み検索
        </h2>
        <span className="text-sm text-[var(--color-text-secondary)]">
          {resultCount}件の動物
        </span>
      </div>

      {/* フィルタフォーム */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* カテゴリフィルタ */}
        <div>
          <label
            htmlFor="category-filter"
            className="block text-sm font-medium text-[var(--color-text-primary)] mb-2"
          >
            カテゴリ
          </label>
          <select
            id="category-filter"
            value={filters.category || ''}
            onChange={(e) =>
              onFilterChange('category', e.target.value || undefined)
            }
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-[var(--color-focus-ring)] min-h-[44px]"
          >
            <option value="">すべて</option>
            <option value="adoption">譲渡対象</option>
            <option value="lost">迷子</option>
          </select>
        </div>

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
  );
}
