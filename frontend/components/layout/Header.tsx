/**
 * Header Component
 * ランドマーク要素 <header> を使用したアクセシブルなヘッダー
 */

import Link from 'next/link';

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
            <ul className="flex space-x-4">
              <li>
                <Link
                  href="/"
                  className="text-[var(--color-text-secondary)] hover:text-[var(--color-primary-700)] transition-colors"
                >
                  動物一覧
                </Link>
              </li>
            </ul>
          </nav>
        </div>
      </div>
    </header>
  );
}
