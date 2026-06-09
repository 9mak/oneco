'use client';

import { useEffect, useRef, useTransition } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { FilterState } from '@/types/animal';

const SEARCH_DEBOUNCE_MS = 300;

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
}

/**
 * UI タブ ＝ ユーザーの意図
 *
 * - 'sheltered': 収容中の子を探す（status=sheltered。category 制約なし → 全種別）
 * - 'adoption':  家族を迎える（category=adoption。里親希望者向け）
 * - 'lost':      迷子情報（category=lost。飼い主が探している子）
 */
type TabValue = 'sheltered' | 'adoption' | 'lost';

const TABS: { value: TabValue; label: string }[] = [
  { value: 'sheltered', label: '収容中の子を探す' },
  { value: 'adoption', label: '家族を迎える' },
  { value: 'lost', label: '迷子情報' },
];

function filtersToTab(filters: FilterState): TabValue {
  if (filters.category === 'adoption') return 'adoption';
  if (filters.category === 'lost') return 'lost';
  return 'sheltered';
}

const STATUS_LABELS: Record<string, string> = {
  adopted: '譲渡済',
  returned: '返還済',
  deceased: '死亡',
};

/** 適用中フィルタをチップ表示用に列挙（カテゴリはタブ・並び替えは別UIなので除外） */
function activeChips(filters: FilterState): { key: keyof FilterState; label: string }[] {
  const chips: { key: keyof FilterState; label: string }[] = [];
  if (filters.species) chips.push({ key: 'species', label: filters.species });
  if (filters.sex) chips.push({ key: 'sex', label: filters.sex });
  if (filters.prefecture) chips.push({ key: 'prefecture', label: filters.prefecture });
  if (filters.location) chips.push({ key: 'location', label: filters.location });
  if (filters.q) chips.push({ key: 'q', label: `「${filters.q}」` });
  if (filters.status && filters.status !== 'sheltered') {
    chips.push({ key: 'status', label: STATUS_LABELS[filters.status] ?? filters.status });
  }
  return chips;
}

export function FilterPanel({ filters }: FilterPanelProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  // フィルタ変更を transition で包むと、Suspense の再サスペンドを待つ間も
  // 前のグリッドを保持したまま裏で差し替えられる（全消しスケルトンのチラつき防止）。
  // isPending を「更新中」インジケータに使う。
  const [isPending, startTransition] = useTransition();

  const updateParam = (key: keyof FilterState, value: string | undefined) => {
    const newParams = new URLSearchParams(searchParams.toString());
    if (value) {
      newParams.set(key, value);
    } else {
      newParams.delete(key);
    }
    const qs = newParams.toString();
    startTransition(() => {
      router.replace(qs ? `?${qs}` : '/', { scroll: false });
    });
  };

  // キーワード検索はキーストローク毎のナビゲーションを避けるため debounce する。
  // また IME 変換中 (Composition) は同期しない — router.replace で親
  // <Suspense key={filters}> が再マウントすると、変換中の文字とフォーカスが
  // 失われ日本語入力が実用に耐えない。確定 (onCompositionEnd) で初めて同期する。
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isComposingRef = useRef(false);
  useEffect(() => {
    return () => {
      if (searchTimer.current) clearTimeout(searchTimer.current);
    };
  }, []);

  const handleSearchChange = (value: string) => {
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => {
      updateParam('q', value.trim() || undefined);
    }, SEARCH_DEBOUNCE_MS);
  };

  const clearAll = () => {
    startTransition(() => {
      router.replace('/', { scroll: false });
    });
  };

  // 'sheltered' タブは default 状態。category 未指定 = 'sheltered' タブ active と等価。
  // status のデフォルト 'sheltered' は明示フィルタとはみなさない。
  const hasActiveFilters = Boolean(
    filters.category ||
      filters.species ||
      filters.sex ||
      filters.location ||
      filters.prefecture ||
      filters.q ||
      (filters.status && filters.status !== 'sheltered'),
  );

  const activeTab = filtersToTab(filters);
  const chips = activeChips(filters);

  const handleTabClick = (tab: TabValue) => {
    if (tab === 'sheltered') {
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
                  ? 'border-b-2 border-[var(--color-primary-700)] text-[var(--color-primary-700)] bg-white'
                  : 'text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-gray-50',
              ].join(' ')}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      <div className="p-6 space-y-4">
        <div className="flex items-center justify-between gap-4 min-h-[1.75rem]">
          <span
            className="text-sm text-[var(--color-text-secondary)]"
            aria-live="polite"
            aria-atomic="true"
          >
            {isPending && (
              <span className="inline-flex items-center gap-2">
                <span
                  className="inline-block w-3.5 h-3.5 border-2 border-current border-t-transparent rounded-full animate-spin"
                  aria-hidden="true"
                />
                更新中…
              </span>
            )}
          </span>
          <div className="flex items-center gap-2">
            <label
              htmlFor="sort-order"
              className="text-sm text-[var(--color-text-secondary)] shrink-0"
            >
              並び替え
            </label>
            <select
              id="sort-order"
              value={filters.sort || 'newest'}
              onChange={(e) =>
                updateParam('sort', e.target.value === 'newest' ? undefined : e.target.value)
              }
              className="px-2 py-1 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-[var(--color-focus-ring)] min-h-[44px]"
            >
              <option value="newest">収容日が新しい順</option>
              <option value="oldest">収容日が古い順</option>
            </select>
          </div>
        </div>

        {/* 適用中フィルタのチップ */}
        {chips.length > 0 && (
          <ul className="flex flex-wrap gap-2" aria-label="適用中の絞り込み">
            {chips.map((chip) => (
              <li key={chip.key}>
                <button
                  onClick={() => updateParam(chip.key, undefined)}
                  className="inline-flex items-center gap-1 px-3 py-1.5 text-sm rounded-full bg-[var(--color-primary-50)] text-[var(--color-primary-800)] border border-[var(--color-primary-100)] hover:bg-[var(--color-primary-100)] transition-colors focus:outline-none focus:ring-2 focus:ring-[var(--color-focus-ring)]"
                  aria-label={`${chip.label} の絞り込みを解除`}
                >
                  <span>{chip.label}</span>
                  <span aria-hidden="true" className="text-base leading-none">
                    ×
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}

        {/* キーワード検索 */}
        <div>
          <label htmlFor="q-search" className="sr-only">
            キーワード検索
          </label>
          <div className="relative">
            <span
              className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-secondary)]"
              aria-hidden="true"
            >
              🔍
            </span>
            <input
              id="q-search"
              type="search"
              defaultValue={filters.q || ''}
              onChange={(e) => {
                // IME 変換確定前は同期しない (確定文字だけを検索語にする)
                if (!isComposingRef.current) {
                  handleSearchChange(e.target.value);
                }
              }}
              onCompositionStart={() => {
                isComposingRef.current = true;
              }}
              onCompositionEnd={(e) => {
                isComposingRef.current = false;
                handleSearchChange((e.target as HTMLInputElement).value);
              }}
              placeholder="例: 茶白、子犬、四万十町..."
              maxLength={100}
              className="w-full pl-10 pr-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-[var(--color-focus-ring)] min-h-[44px]"
            />
          </div>
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
