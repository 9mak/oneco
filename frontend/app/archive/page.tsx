import type { Metadata } from 'next';
import { fetchArchivedAnimals } from '@/lib/archive';
import { ArchivedAnimalCard } from '@/components/animals/ArchivedAnimalCard';
import { EmptyState } from '@/components/ui/EmptyState';
import type { ArchivedAnimalPublic } from '@/types/animal';

export const revalidate = 1800;

export const metadata: Metadata = {
  title: '卒業した子たち',
  description:
    '新しい家族のもとへ譲渡された、あるいは元の飼い主のもとへ戻った動物たちの記録。oneco を通じて出会いが生まれた子たちを紹介します。',
  alternates: { canonical: '/archive' },
  openGraph: {
    type: 'website',
    title: '卒業した子たち | oneco',
    description: '譲渡・返還で家族のもとへ戻った子たちの記録',
    url: '/archive',
  },
};

const PAGE_SIZE = 24;

export default async function ArchivePage() {
  let items: ArchivedAnimalPublic[] = [];
  let totalCount = 0;
  try {
    const data = await fetchArchivedAnimals({ limit: PAGE_SIZE, offset: 0 });
    items = data.items;
    totalCount = data.meta.total_count;
  } catch (error) {
    console.error('Failed to fetch archived animals:', error);
  }

  return (
    <div className="container mx-auto px-4 py-8 space-y-8">
      <section
        aria-label="卒業した子たちについて"
        className="rounded-2xl bg-gradient-to-br from-[var(--color-accent-50)] via-white to-[var(--color-primary-50)] border border-[var(--color-accent-100)] p-6 sm:p-10"
      >
        <h1 className="text-2xl sm:text-3xl font-bold text-[var(--color-text-primary)] leading-snug">
          🎉 卒業した子たち
        </h1>
        <p className="mt-3 text-sm sm:text-base text-[var(--color-text-secondary)] leading-relaxed max-w-3xl">
          oneco に掲載されていた動物のうち、新しい家族のもとへ譲渡された子、
          または元の飼い主のもとへ無事戻った子たちの記録です。
          このページの子たちはすでに卒業しているため、お問い合わせは受け付けていません。
        </p>
        {totalCount > 0 && (
          <p className="mt-4 text-sm text-[var(--color-accent-700)] font-medium">
            これまでに {totalCount} 件の出会いが生まれました
          </p>
        )}
      </section>

      {items.length === 0 ? (
        <EmptyState
          message="まだ卒業した子の記録はありません"
          suggestion="譲渡・返還が成立した動物は、一定期間経過後にこちらへ記録されます。"
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
          {items.map((animal) => (
            <ArchivedAnimalCard key={animal.id} animal={animal} />
          ))}
        </div>
      )}
    </div>
  );
}
