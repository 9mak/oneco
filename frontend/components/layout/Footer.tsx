import Link from 'next/link';

/**
 * Footer Component
 * ランドマーク要素 <footer> を使用したアクセシブルなフッター
 */

export function Footer() {
  return (
    <footer className="bg-gray-50 border-t border-gray-200 mt-auto">
      <div className="container mx-auto px-4 py-8">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          <section>
            <h2 className="text-lg font-semibold text-[var(--color-text-primary)] mb-4">
              このサイトについて
            </h2>
            <p className="text-sm text-[var(--color-text-secondary)]">
              本サイトは保護動物情報を提供する非営利サービスです。
              動物の譲渡や引き取りについては、各自治体の動物愛護センターに直接お問い合わせください。
            </p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-[var(--color-text-primary)] mb-4">
              免責事項
            </h2>
            <p className="text-sm text-[var(--color-text-secondary)]">
              掲載されている動物情報は各自治体サイトから収集したものです。
              最新の正確な情報については、必ず元のページ（自治体の公式サイト）をご確認ください。
              本サイトの情報の正確性について、一切の責任を負いかねます。
            </p>
          </section>
        </div>

        <nav
          className="mt-8 pt-4 border-t border-gray-200 flex flex-wrap justify-center gap-x-6 gap-y-2 text-sm"
          aria-label="フッターナビゲーション"
        >
          <Link
            href="/privacy"
            className="text-[var(--color-text-secondary)] hover:text-[var(--color-primary-500)] hover:underline"
          >
            プライバシーポリシー
          </Link>
          <Link
            href="/terms"
            className="text-[var(--color-text-secondary)] hover:text-[var(--color-primary-500)] hover:underline"
          >
            利用規約
          </Link>
          <a
            href="https://github.com/9mak/oneco"
            target="_blank"
            rel="noopener noreferrer"
            className="text-[var(--color-text-secondary)] hover:text-[var(--color-primary-500)] hover:underline"
          >
            GitHub
          </a>
        </nav>

        <div className="mt-4 text-center">
          <p className="text-sm text-[var(--color-text-secondary)]">
            &copy; 2026 oneco - 保護動物情報ポータル. All rights reserved.
          </p>
        </div>
      </div>
    </footer>
  );
}
