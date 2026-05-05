import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '利用規約',
  description:
    'oneco（保護動物情報ポータル）の利用規約。当サイトの利用条件と免責事項についてご説明します。',
  alternates: { canonical: '/terms' },
};

export default function TermsPage() {
  return (
    <article className="container mx-auto px-4 py-12 max-w-3xl prose prose-sm md:prose-base">
      <h1 className="text-2xl md:text-3xl font-bold mb-6">利用規約</h1>
      <p className="text-sm text-[var(--color-text-secondary)] mb-8">
        最終更新日: 2026年5月6日
      </p>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">1. サイトの目的</h2>
        <p>
          oneco（以下「当サイト」）は、全国の自治体に保護されている犬・猫の情報を一元化し、
          譲渡や飼い主の発見を支援する非営利のポータルサイトです。
        </p>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">2. 情報の出典と正確性</h2>
        <p>
          当サイトに掲載されている動物情報は、各自治体の公式サイトから自動収集した公開情報です。
          掲載情報には誤りやタイムラグがある可能性があります。最新かつ正確な情報については、
          必ず元の公式ページをご確認ください。
        </p>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">3. 譲渡・引き取りに関するお問い合わせ</h2>
        <p>
          動物の譲渡や引き取りについては、当サイトでは仲介を行いません。
          各動物の詳細ページに記載された自治体の動物愛護センター等に直接お問い合わせください。
        </p>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">4. 免責事項</h2>
        <ul className="list-disc ml-6">
          <li>当サイトは、掲載情報の正確性・完全性・最新性について一切保証しません</li>
          <li>当サイトの利用により生じたいかなる損害についても責任を負いません</li>
          <li>掲載動物の譲渡可否や状態は元サイトの情報を優先してください</li>
          <li>当サイトのサービスは予告なく変更・停止することがあります</li>
        </ul>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">5. 禁止事項</h2>
        <ul className="list-disc ml-6">
          <li>掲載情報を商業目的で無断利用すること</li>
          <li>当サイトのサーバーやネットワークに過度な負荷を与える行為</li>
          <li>掲載されている動物の所有者・関係者を誹謗中傷する行為</li>
          <li>その他、法令や公序良俗に反する行為</li>
        </ul>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">6. 著作権・データの利用</h2>
        <p>
          動物の画像・情報の著作権は各自治体・元サイトの管理者に帰属します。
          当サイトのコード（オープンソース）は
          <a
            href="https://github.com/9mak/oneco"
            target="_blank"
            rel="noopener noreferrer"
            className="text-[var(--color-primary-500)] hover:underline"
          >
            GitHub
          </a>
          で公開されています。
        </p>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">7. 規約の変更</h2>
        <p>
          本規約は予告なく改訂されることがあります。改訂後も継続して当サイトを利用する場合、
          改訂後の規約に同意したものとみなします。
        </p>
      </section>

      <section>
        <h2 className="text-xl font-semibold mb-3">8. お問い合わせ</h2>
        <p>
          本規約に関するお問い合わせは、
          <a
            href="https://github.com/9mak/oneco/issues"
            target="_blank"
            rel="noopener noreferrer"
            className="text-[var(--color-primary-500)] hover:underline"
          >
            GitHub Issues
          </a>
          までお寄せください。
        </p>
      </section>
    </article>
  );
}
