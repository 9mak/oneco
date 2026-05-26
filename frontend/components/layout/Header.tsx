/**
 * Header Component
 * ランドマーク要素 <header> を使用したアクセシブルなヘッダー
 */

'use client';

import Link from 'next/link';
import { useFavorites } from '@/lib/favorites';

function FavoritesLink() {
  const { favorites } = useFavorites();
  return (
    <Link
      href="/favorites"
      className="relative text-[var(--color-text-secondary)] hover:text-[var(--color-primary-700)] transition-colors flex items-center gap-1"
      aria-label={`お気に入り (${favorites.length}件)`}
    >
      <svg
        xmlns="http://www.w3.org/2000/svg"
        width={18}
        height={18}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
      </svg>
      <span>お気に入り</span>
      {favorites.length > 0 && (
        <span className="ml-1 inline-flex items-center justify-center min-w-[20px] h-5 px-1 text-xs font-semibold bg-red-500 text-white rounded-full">
          {favorites.length}
        </span>
      )}
    </Link>
  );
}

export function Header() {
  return (
    <header className="bg-white border-b border-gray-200">
      <div className="container mx-auto px-4 py-4">
        <div className="flex items-center justify-between">
          {/* ロゴとサイトタイトル */}
          <Link href="/" className="flex items-center space-x-2">
            <h1 className="text-2xl font-bold text-[var(--color-text-primary)]">
              oneco
            </h1>
          </Link>

          {/* ナビゲーション */}
          <nav aria-label="メインナビゲーション">
            <ul className="flex items-center space-x-4">
              <li>
                <Link
                  href="/"
                  className="text-[var(--color-text-secondary)] hover:text-[var(--color-primary-700)] transition-colors"
                >
                  動物一覧
                </Link>
              </li>
              <li>
                <FavoritesLink />
              </li>
            </ul>
          </nav>
        </div>
      </div>
    </header>
  );
}
