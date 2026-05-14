import type { Metadata } from 'next';

import {
  PublicStatsError,
  fetchPublicStats,
  type PublicStats,
} from '@/lib/public-stats';

export const revalidate = 300;

export const metadata: Metadata = {
  title: 'oneco の実績 - 全国保護動物プラットフォーム',
  description:
    'oneco は全国の動物愛護センター情報を横断検索できるプラットフォームです。累計掲載動物数、対応自治体数、対応サイト数を公開しています。',
  openGraph: {
    title: 'oneco の実績',
    description:
      '全国の保護動物情報を一つに。殺処分ゼロへ向けた oneco の活動メトリクス。',
    type: 'website',
  },
};

export default async function PublicStatsPage() {
  let stats: PublicStats | null = null;
  let error: string | null = null;

  try {
    stats = await fetchPublicStats({ revalidateSec: 300 });
  } catch (e) {
    error =
      e instanceof PublicStatsError
        ? '実績データを読み込めませんでした'
        : '実績データの取得に失敗しました';
  }

  return (
    <main className="mx-auto max-w-4xl px-4 py-12">
      <header className="mb-10 text-center">
        <h1 className="text-3xl font-bold text-[var(--color-text-primary)] sm:text-4xl">
          oneco の実績
        </h1>
        <p className="mt-3 text-base text-[var(--color-text-secondary)]">
          全国の保護動物情報を一つに集約しています。
        </p>
      </header>

      {error && (
        <div
          role="alert"
          className="mb-8 rounded border border-red-300 bg-red-50 p-4 text-red-900"
        >
          {error}
        </div>
      )}

      {stats && (
        <section
          aria-label="累計実績メトリクス"
          className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4"
        >
          <StatCard
            label="累計掲載動物"
            value={stats.total_animals.toLocaleString('ja-JP')}
            unit="頭"
          />
          <StatCard
            label="対応自治体"
            value={stats.municipality_count.toLocaleString('ja-JP')}
            unit="都道府県"
          />
          <StatCard
            label="対応サイト"
            value={stats.site_count.toLocaleString('ja-JP')}
            unit="サイト"
          />
          <StatCard
            label="平均待機日数"
            value={
              stats.avg_waiting_days != null
                ? stats.avg_waiting_days.toFixed(0)
                : '—'
            }
            unit={stats.avg_waiting_days != null ? '日' : ''}
          />
        </section>
      )}

      <section className="mt-12 rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        <h2 className="mb-3 text-lg font-semibold text-[var(--color-text-primary)]">
          このプロジェクトについて
        </h2>
        <p className="text-sm leading-relaxed text-[var(--color-text-secondary)]">
          oneco は、全国 100 以上の自治体・愛護センターの保護動物情報を AI
          で自動収集し、統一された検索 UI で提供するオープンソースプロジェクトです。
          目標は <strong>「殺処分ゼロ」</strong> に貢献すること。
        </p>
      </section>
    </main>
  );
}

function StatCard({
  label,
  value,
  unit,
}: {
  label: string;
  value: string;
  unit: string;
}) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
      <div className="text-sm font-medium text-[var(--color-text-secondary)]">
        {label}
      </div>
      <div className="mt-2 flex items-baseline gap-1">
        <span className="text-3xl font-bold tabular-nums text-[var(--color-text-primary)]">
          {value}
        </span>
        {unit && (
          <span className="text-sm text-[var(--color-text-secondary)]">
            {unit}
          </span>
        )}
      </div>
    </div>
  );
}
