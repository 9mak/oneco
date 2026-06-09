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
    <header className="sticky top-0 z-50 bg-white/95 backdrop-blur supports-[backdrop-filter]:bg-white/80 border-b border-gray-200">
      <div className="container mx-auto px-4 py-3 sm:py-4">
        <div className="flex items-center justify-between gap-4">
          {/* ロゴ + プロダクト説明 */}
          <Link
            href="/"
            className="flex items-center gap-2 sm:gap-3 min-w-0 focus:outline-none focus:ring-2 focus:ring-[var(--color-focus-ring)] focus:ring-offset-2 rounded"
            aria-label="oneco トップへ"
          >
            <span
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[var(--color-accent-100)]"
              aria-hidden="true"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width={20}
                height={20}
                viewBox="0 0 24 24"
                fill="none"
                stroke="var(--color-accent-700)"
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <circle cx="11" cy="4" r="2" />
                <circle cx="18" cy="8" r="2" />
                <circle cx="20" cy="16" r="2" />
                <path d="M9 10a5 5 0 0 1 5 5v3.5a3.5 3.5 0 0 1-6.84 1.045Q6.52 17.48 4.46 16.84A3.5 3.5 0 0 1 5.5 10Z" />
              </svg>
            </span>
            <span className="flex flex-col sm:flex-row sm:items-baseline gap-0.5 sm:gap-2 min-w-0">
              {/* a11y: ロゴは h1 ではなく span。h1 は各ページの主見出しに譲る */}
              <span className="text-2xl font-bold text-[var(--color-text-primary)] leading-none">
                oneco
              </span>
              <span className="hidden sm:inline text-xs sm:text-sm text-[var(--color-text-secondary)] truncate">
                全国の保護動物情報をひとつに
              </span>
            </span>
          </Link>

          {/* ナビゲーション */}
          <nav aria-label="メインナビゲーション" className="shrink-0">
            <ul className="flex items-center gap-3 sm:gap-4">
              {/* 「動物一覧」はロゴと同じ / へのリンクなのでモバイルでは省略 */}
              <li className="hidden sm:block">
                <Link
                  href="/"
                  className="text-[var(--color-text-secondary)] hover:text-[var(--color-primary-700)] transition-colors focus:outline-none focus:ring-2 focus:ring-[var(--color-focus-ring)] focus:ring-offset-2 rounded px-1"
                >
                  動物一覧
                </Link>
              </li>
              <li>
                <Link
                  href="/archive"
                  aria-label="卒業した子たち"
                  className="text-[var(--color-text-secondary)] hover:text-[var(--color-primary-700)] transition-colors focus:outline-none focus:ring-2 focus:ring-[var(--color-focus-ring)] focus:ring-offset-2 rounded px-1"
                >
                  {/* モバイルでは短縮表示して横幅を節約。SR には aria-label で常にフルラベルを伝える */}
                  <span className="sm:hidden" aria-hidden="true">卒業</span>
                  <span className="hidden sm:inline">卒業した子たち</span>
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
