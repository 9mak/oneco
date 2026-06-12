import type { Metadata } from 'next';
import Link from 'next/link';
import sitesData from '@/data/transparency-sites.json';

export const metadata: Metadata = {
  title: '運営方針・データソース・撤去依頼',
  description:
    'oneco（保護動物情報ポータル）の運営方針、データソース一覧（47 都道府県・91 ホスト）、著作権スタンス、撤去依頼の窓口について。',
  alternates: { canonical: '/transparency' },
};

interface SiteEntry {
  name: string;
  host: string;
  url: string;
}

interface TransparencyPayload {
  total_sources: number;
  total_prefectures: number;
  total_hosts: number;
  by_prefecture: Record<string, SiteEntry[]>;
}

const data = sitesData as TransparencyPayload;

export default function TransparencyPage() {
  const prefectures = Object.keys(data.by_prefecture);

  return (
    <article className="container mx-auto px-4 py-12 max-w-4xl prose prose-sm md:prose-base">
      <h1 className="text-2xl md:text-3xl font-bold mb-6">運営方針・データソース・撤去依頼</h1>
      <p className="text-sm text-[var(--color-text-secondary)] mb-8">
        最終更新日: 2026年6月12日
      </p>

      <section className="mb-10">
        <h2 className="text-xl font-semibold mb-3">1. oneco について</h2>
        <p>
          oneco は、各自治体が公開している保護動物（譲渡対象・収容中・迷子）の情報を全国規模で集約し、
          里親候補・飼い主に届けることを目的とする非営利のポータルサイトです。
          殺処分ゼロに近づけるための情報の流通を支援することを使命としています。
        </p>
        <p>
          掲載情報の一次ソースは各自治体の公式サイトであり、本サイトは公式情報への案内・補助を行う立場です。
          詳細・最新情報は必ず各自治体の公式ページをご確認ください。
        </p>
      </section>

      <section className="mb-10">
        <h2 className="text-xl font-semibold mb-3">2. データソース</h2>
        <p>
          現在、
          <strong>{data.total_prefectures} 都道府県</strong>・
          <strong>{data.total_hosts} ホスト</strong>・
          <strong>{data.total_sources} ソース</strong>
          から情報を収集しています。
        </p>

        <details className="my-4">
          <summary className="cursor-pointer text-[var(--color-primary-700)] hover:underline">
            全データソース一覧を表示
          </summary>
          <div className="mt-4 space-y-6">
            {prefectures.map((pref) => (
              <div key={pref}>
                <h3 className="text-base font-semibold mb-2">{pref}</h3>
                <ul className="list-disc ml-6 space-y-1 text-sm">
                  {data.by_prefecture[pref].map((site) => (
                    <li key={site.url}>
                      <a
                        href={site.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-[var(--color-primary-700)] hover:underline"
                      >
                        {site.name}
                      </a>
                      <span className="ml-2 text-xs text-[var(--color-text-secondary)]">
                        ({site.host})
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </details>
      </section>

      <section className="mb-10">
        <h2 className="text-xl font-semibold mb-3">3. 収集ポリシー</h2>
        <ul className="list-disc ml-6 space-y-1">
          <li>各自治体サイトの <code>robots.txt</code> を尊重し、許可されたページのみ取得します</li>
          <li>
            User-Agent に <code>ONECO_USER_AGENT</code> を明示し、本サイトからのアクセスであることを開示します
          </li>
          <li>同一ホストへのアクセス間隔を最低 1 秒以上空けて、サーバ負荷をかけないよう配慮しています</li>
          <li>収集頻度は 1 日 1 回（深夜帯）で、過剰なクロールは行いません</li>
          <li>取得対象は公開情報のみで、認証が必要なページや非公開エリアにはアクセスしません</li>
        </ul>
      </section>

      <section className="mb-10">
        <h2 className="text-xl font-semibold mb-3">4. 著作権・情報の取り扱い</h2>
        <p>
          本サイトは、各自治体が <strong>公開している事実情報を集約・案内</strong> する立場のサイトです。
          各動物情報の写真・本文に関する著作権は、原則として各自治体に帰属します。
        </p>
        <ul className="list-disc ml-6 space-y-1 mt-2">
          <li>
            <strong>写真</strong>: 本サイトでは画像の自前ホスティングは行わず、各自治体公式サイトの画像 URL を直接参照する形で表示しています
          </li>
          <li>
            <strong>本文</strong>: 個体特徴・収容情報などの事実情報を要約・整形して掲載しています。引用範囲を超える長文転載は行いません
          </li>
          <li>
            <strong>個人情報</strong>: 自治体が公開している情報のうち、発見者の個人連絡先など個人を特定し得る情報は
            自動的に除去（マスキング）した上で掲載します
          </li>
        </ul>
      </section>

      <section className="mb-10">
        <h2 className="text-xl font-semibold mb-3">5. 撤去依頼・修正依頼の窓口</h2>
        <p>
          掲載内容に関するご懸念がある場合（撤去・修正・著作権主張等）は、以下の窓口までご連絡ください。
        </p>
        <ul className="list-disc ml-6 space-y-2 mt-3">
          <li>
            <strong>GitHub Issues</strong>:
            <a
              href="https://github.com/9mak/oneco/issues/new?template=takedown-request.yml"
              target="_blank"
              rel="noopener noreferrer"
              className="ml-2 text-[var(--color-primary-700)] hover:underline"
            >
              撤去依頼テンプレートから報告
            </a>
            <span className="block text-xs text-[var(--color-text-secondary)] mt-1">
              テンプレートでは自治体名・対象 URL・申立理由・連絡先メールを入力していただきます。
            </span>
          </li>
          <li>
            <strong>メール</strong>: GitHub Issues を使用したくない場合は、運営者プロフィール
            （
            <a
              href="https://github.com/9mak"
              target="_blank"
              rel="noopener noreferrer"
              className="text-[var(--color-primary-700)] hover:underline"
            >
              @9mak
            </a>
            ）の公開連絡先までご連絡ください。
          </li>
        </ul>

        <div className="mt-6 p-4 bg-[var(--color-primary-50)] border-l-4 border-[var(--color-primary-700)] rounded">
          <p className="font-semibold mb-1">対応 SLA</p>
          <p className="text-sm">
            撤去依頼の申し立てから <strong>7 営業日以内</strong> に対応状況をご返答します。
            内容を確認の上、適切と判断した場合は速やかに該当データを非公開化します。
          </p>
        </div>
      </section>

      <section className="mb-10">
        <h2 className="text-xl font-semibold mb-3">6. 法的姿勢のサマリ</h2>
        <p>
          本サイトの運営は以下の方針に基づいています:
        </p>
        <ul className="list-disc ml-6 space-y-1 mt-2">
          <li><strong>無償・非営利</strong>: 広告・有料機能を提供せず、運営は寄付を含む非営利ベースです</li>
          <li><strong>事実情報中心</strong>: 評価・意見・スコアリングを伴わず、公開情報の集約のみを行います</li>
          <li><strong>出典明示</strong>: 各動物情報には必ず元の自治体公式ページへのリンクを併記します</li>
          <li><strong>撤去対応窓口の常設</strong>: 上記 5 の窓口を継続的に運営し、申立てに誠実に対応します</li>
          <li><strong>営利化の保留</strong>: マネタイズ（広告・有料化・物販等）を行う際は、事前に専門家に相談し、必要な場合は方針を見直します</li>
        </ul>
      </section>

      <section className="mb-10">
        <h2 className="text-xl font-semibold mb-3">7. 運営者・連絡先</h2>
        <p>
          個人運営のプロジェクトです。連絡は前述の GitHub Issues または GitHub プロフィール経由でお願いします。
        </p>
        <ul className="list-disc ml-6 space-y-1 mt-2">
          <li>GitHub: <a href="https://github.com/9mak/oneco" target="_blank" rel="noopener noreferrer" className="text-[var(--color-primary-700)] hover:underline">9mak/oneco</a></li>
          <li>関連: <Link href="/about" className="text-[var(--color-primary-700)] hover:underline">このサイトについて</Link></li>
        </ul>
      </section>

      <section>
        <h2 className="text-xl font-semibold mb-3">8. 改訂履歴</h2>
        <ul className="list-disc ml-6 space-y-1">
          <li>2026年6月12日: 初版公開</li>
        </ul>
      </section>
    </article>
  );
}
