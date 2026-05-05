import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'プライバシーポリシー',
  description:
    'oneco（保護動物情報ポータル）のプライバシーポリシー。当サイトでの個人情報の取り扱いについてご説明します。',
  alternates: { canonical: '/privacy' },
};

export default function PrivacyPage() {
  return (
    <article className="container mx-auto px-4 py-12 max-w-3xl prose prose-sm md:prose-base">
      <h1 className="text-2xl md:text-3xl font-bold mb-6">プライバシーポリシー</h1>
      <p className="text-sm text-[var(--color-text-secondary)] mb-8">
        最終更新日: 2026年5月6日
      </p>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">1. 基本方針</h2>
        <p>
          oneco（以下「当サイト」）は、保護動物情報を一元化して提供する非営利のポータルサイトです。
          利用者のプライバシー保護を最重要事項と位置付け、本ポリシーに従って個人情報を取り扱います。
        </p>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">2. 収集する情報</h2>
        <p>
          当サイトは、利用者が情報を閲覧する際にアカウント登録や個人情報の入力を求めません。
          ただし、以下のアクセス情報を自動的に取得する場合があります。
        </p>
        <ul className="list-disc ml-6 mt-2">
          <li>IPアドレス、ブラウザ種別、リファラ情報（アクセス解析のため）</li>
          <li>Cookie（ユーザー体験向上のため。お気に入り機能を実装した場合の設定保存等）</li>
        </ul>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">3. 情報の利用目的</h2>
        <ul className="list-disc ml-6">
          <li>サイトの運営・改善のため</li>
          <li>アクセス傾向の分析のため</li>
          <li>不正アクセスや障害の検知のため</li>
        </ul>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">4. 第三者への提供</h2>
        <p>
          当サイトは、法令に基づく場合を除き、取得した情報を本人の同意なく第三者に提供しません。
        </p>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">5. 外部サービスの利用</h2>
        <p>
          当サイトは以下の外部サービスを利用しています。各サービスのプライバシーポリシーが適用されます。
        </p>
        <ul className="list-disc ml-6 mt-2">
          <li>Vercel（ホスティング）</li>
          <li>Google Cloud Platform（API バックエンド）</li>
          <li>Supabase（データベース）</li>
        </ul>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">6. 動物情報の取り扱い</h2>
        <p>
          当サイトに掲載されている動物情報は、各自治体の公式サイトから取得した公開情報です。
          掲載に関するお問い合わせは、各自治体の動物愛護センターに直接ご連絡ください。
        </p>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-3">7. ポリシーの変更</h2>
        <p>
          本ポリシーは予告なく改訂されることがあります。変更後の内容は当サイトに掲載した時点で効力を生じるものとします。
        </p>
      </section>

      <section>
        <h2 className="text-xl font-semibold mb-3">8. お問い合わせ</h2>
        <p>
          本ポリシーに関するお問い合わせは、
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
