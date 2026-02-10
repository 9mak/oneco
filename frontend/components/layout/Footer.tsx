/**
 * Footer Component
 * ランドマーク要素 <footer> を使用したアクセシブルなフッター
 * 利用規約と免責事項を表示
 */

export function Footer() {
  return (
    <footer className="bg-gray-50 border-t border-gray-200 mt-auto">
      <div className="container mx-auto px-4 py-8">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          {/* 利用規約 */}
          <section>
            <h2 className="text-lg font-semibold text-[var(--color-text-primary)] mb-4">
              利用規約
            </h2>
            <p className="text-sm text-[var(--color-text-secondary)]">
              本サイトは保護動物情報を提供する非営利サービスです。
              動物の譲渡や引き取りについては、各自治体の動物愛護センターに直接お問い合わせください。
            </p>
          </section>

          {/* 免責事項 */}
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

        <div className="mt-8 pt-4 border-t border-gray-200 text-center">
          <p className="text-sm text-[var(--color-text-secondary)]">
            &copy; 2026 OneCoアニマルポータル. All rights reserved.
          </p>
        </div>
      </div>
    </footer>
  );
}
