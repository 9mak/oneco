import { notFound } from 'next/navigation';
import Link from 'next/link';
import type { Metadata } from 'next';
import { fetchAnimals } from '@/lib/animals';
import { AnimalGrid } from '@/components/animals/AnimalGrid';
import { PREFECTURES, isValidPrefecture } from '@/lib/prefectures';
import { getSiteUrl } from '@/lib/site-url';
import type { AnimalPublic, FilterState } from '@/types/animal';

// 各都道府県ページは ISR。事前生成 + 5 分ごとに再検証する。
export const revalidate = 300;

const PAGE_SIZE = 20;
const SITE_URL = getSiteUrl();

interface PrefecturePageProps {
  params: Promise<{ prefecture: string }>;
}

/** 47 都道府県を build 時に事前生成する（generateStaticParams）。 */
export function generateStaticParams(): { prefecture: string }[] {
  return PREFECTURES.map((prefecture) => ({ prefecture }));
}

/** URL セグメントをデコードして正式な都道府県名を返す。不正なら null。 */
function resolvePrefecture(raw: string): string | null {
  let decoded: string;
  try {
    decoded = decodeURIComponent(raw);
  } catch {
    return null;
  }
  return isValidPrefecture(decoded) ? decoded : null;
}

export async function generateMetadata({ params }: PrefecturePageProps): Promise<Metadata> {
  const { prefecture } = await params;
  const pref = resolvePrefecture(prefecture);
  if (!pref) {
    return { title: '地域が見つかりません' };
  }

  const title = `${pref}の保護犬・保護猫の里親募集一覧`;
  const description = `${pref}の自治体に収容されている保護犬・保護猫の情報をまとめています。種別・性別で絞り込んで、新しい家族を待っている子を探せます。`;
  const canonical = `${SITE_URL}/areas/${encodeURIComponent(pref)}`;

  return {
    title,
    description,
    alternates: { canonical },
    openGraph: {
      title: `${title} | oneco`,
      description,
      url: canonical,
      type: 'website',
    },
  };
}

async function fetchPrefectureAnimals(prefecture: string): Promise<{
  items: AnimalPublic[];
  totalCount: number;
  fetchFailed: boolean;
}> {
  const filters: FilterState = { prefecture, status: 'sheltered' };
  try {
    const data = await fetchAnimals({ ...filters, limit: PAGE_SIZE, offset: 0 });
    return { items: data.items, totalCount: data.meta.total_count, fetchFailed: false };
  } catch (error) {
    console.error('Failed to fetch animals:', error);
    return { items: [], totalCount: 0, fetchFailed: true };
  }
}

export default async function PrefecturePage({ params }: PrefecturePageProps) {
  const { prefecture } = await params;
  const pref = resolvePrefecture(prefecture);
  if (!pref) notFound();

  const { items, totalCount, fetchFailed } = await fetchPrefectureAnimals(pref);
  const filters: FilterState = { prefecture: pref, status: 'sheltered' };

  return (
    <div className="container mx-auto px-4 py-8 space-y-6">
      {/* パンくず（BreadcrumbList 相当の導線） */}
      <nav aria-label="パンくず" className="text-sm text-[var(--color-text-secondary)]">
        <Link
          href="/"
          className="underline-offset-2 hover:text-[var(--color-primary-700)] hover:underline"
        >
          ホーム
        </Link>
        <span aria-hidden="true" className="mx-2">
          /
        </span>
        <span aria-current="page" className="text-[var(--color-text-primary)]">
          {pref}
        </span>
      </nav>

      <header className="space-y-3">
        <h1 className="text-2xl sm:text-3xl font-bold leading-snug text-[var(--color-text-primary)]">
          {pref}の保護犬・保護猫
        </h1>
        <p className="max-w-3xl text-sm leading-relaxed text-[var(--color-text-secondary)] sm:text-base">
          {pref}の自治体に収容されている、新しい家族を待っている犬・猫の一覧です。
          気になる子がいたら詳細ページから収容先の自治体へお問い合わせください。
        </p>
        <Link
          href={`/?prefecture=${encodeURIComponent(pref)}`}
          className="inline-flex items-center gap-1 text-sm font-medium text-[var(--color-primary-700)] hover:underline"
        >
          地図・条件で絞り込んで探す →
        </Link>
      </header>

      <AnimalGrid
        initialItems={items}
        totalCount={totalCount}
        filters={filters}
        pageSize={PAGE_SIZE}
        fetchFailed={fetchFailed}
      />

      {/* 他都道府県への内部リンク（クロール経路 + 回遊性の確保） */}
      <nav aria-label="他の都道府県から探す" className="border-t border-gray-200 pt-6">
        <h2 className="mb-3 text-sm font-semibold text-[var(--color-text-secondary)]">
          他の都道府県から探す
        </h2>
        <ul className="flex flex-wrap gap-x-4 gap-y-2">
          {PREFECTURES.filter((p) => p !== pref).map((p) => (
            <li key={p}>
              <Link
                href={`/areas/${encodeURIComponent(p)}`}
                className="text-sm text-[var(--color-primary-700)] hover:underline"
              >
                {p}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
    </div>
  );
}
