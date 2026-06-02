'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useFavorites } from '@/lib/favorites';
import { AnimalCard } from '@/components/animals/AnimalCard';
import { AnimalGridSkeleton } from '@/components/animals/AnimalGridSkeleton';
import type { AnimalPublic } from '@/types/animal';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

export default function FavoritesPage() {
  const { favorites } = useFavorites();
  const [animals, setAnimals] = useState<AnimalPublic[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function fetchAll() {
      setLoading(true);
      setError(null);
      try {
        // 404 (= 譲渡済み/削除で元データ消失) と、fetch 自体の失敗 (= サーバー
        // 到達不可) を区別する。前者は「譲渡済み等」の注記、後者はエラー表示。
        const results = await Promise.all(
          favorites.map(async (id) => {
            try {
              const res = await fetch(`${API_BASE_URL}/animals/${id}`);
              if (res.ok) {
                return { kind: 'ok' as const, value: (await res.json()) as AnimalPublic };
              }
              return { kind: 'notfound' as const };
            } catch {
              return { kind: 'error' as const };
            }
          }),
        );
        if (cancelled) return;
        const ok = results
          .filter((r): r is { kind: 'ok'; value: AnimalPublic } => r.kind === 'ok')
          .map((r) => r.value);
        const networkErrors = results.filter((r) => r.kind === 'error').length;
        setAnimals(ok);
        // 1 件も取得できず、原因がネットワーク/サーバー障害なら明示エラー。
        // (全件 404 = 全部譲渡済みのケースは後段の注記で案内する)
        if (ok.length === 0 && networkErrors > 0) {
          setError('一時的に読み込めませんでした');
        }
      } catch (e) {
        if (!cancelled) setError(String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    fetchAll();
    return () => {
      cancelled = true;
    };
  }, [favorites]);

  return (
    <div className="container mx-auto px-4 py-8 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl md:text-3xl font-bold">お気に入りの子たち</h1>
        <p className="text-sm text-[var(--color-text-secondary)]">
          {favorites.length}件
        </p>
      </div>

      {favorites.length === 0 ? (
        <div className="bg-white rounded-lg shadow-md p-8 text-center space-y-4">
          <p className="text-[var(--color-text-primary)]">
            まだお気に入りに追加された子はいません
          </p>
          <p className="text-sm text-[var(--color-text-secondary)]">
            気になる子のカードにある♡をクリックすると、ここに保存されます。
          </p>
          <Link
            href="/"
            className="inline-block px-4 py-2 rounded-md bg-[var(--color-primary-700)] text-white hover:bg-[var(--color-primary-800)] transition-colors"
          >
            動物一覧へ戻る
          </Link>
        </div>
      ) : loading ? (
        <AnimalGridSkeleton />
      ) : error ? (
        <div className="bg-red-50 text-red-700 rounded-md p-4">
          読み込みに失敗しました。時間をおいて再度お試しください。
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
          {animals.map((a) => (
            <AnimalCard key={a.id} animal={a} />
          ))}
          {animals.length < favorites.length && (
            <p className="col-span-full text-sm text-[var(--color-text-secondary)]">
              ※ {favorites.length - animals.length}件は元データが見つかりませんでした（譲渡済み等）
            </p>
          )}
        </div>
      )}
    </div>
  );
}
