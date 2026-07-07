import type { Metadata } from 'next';
import Image from 'next/image';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'このサイトについて',
  description:
    'oneco（保護動物情報ポータル）の活動目的・運営方針・データソースについて。全国 47 都道府県の自治体公開情報を集約し、保護犬・保護猫の里親候補と飼い主に届けることを目指す非営利のポータルサイトです。',
  alternates: { canonical: '/about' },
};

const DATA_SOURCE_COUNTS = {
  prefectures: 47,
  hosts: 91,
  sources: 211,
};

export default function AboutPage() {
  return (
    <article className="container mx-auto px-4 py-12 max-w-3xl prose prose-sm md:prose-base">
      <h1 className="text-2xl md:text-3xl font-bold mb-6">このサイトについて</h1>

      <section className="mb-10">
        <h2 className="text-xl font-semibold mb-3">oneco とは</h2>
        <p>
          oneco は、全国の自治体（動物愛護センター・保健所）が公開している
          保護犬・保護猫の情報を一覧で見られるようにする、非営利のポータルサイトです。
        </p>
        <p className="mt-3">
          現在、
          <strong>{DATA_SOURCE_COUNTS.prefectures} 都道府県</strong>・
          <strong>{DATA_SOURCE_COUNTS.hosts} ホスト</strong>・
          <strong>{DATA_SOURCE_COUNTS.sources} ソース</strong>
          から日次で情報を集約しています。
        </p>
      </section>

      <section className="mb-10">
        <h2 className="text-xl font-semibold mb-3">oneco という名前と、ふたつの円</h2>
        <p>
          oneco（ワンコ）は、「わんこ」の綴りの中に「ねこ（NECO）」がいる名前です。
          頭の ONE には、ばらばらの情報をひとつにという意味も重なっています。
          ロゴのふたつの円は、このサイトのモデルになった犬のポムと猫のビリーを表しています。
        </p>

        <figure className="not-prose m-0 mt-6">
          <div className="grid grid-cols-3 grid-rows-2 gap-2">
            <div className="col-span-2 row-span-2">
              <Image
                src="/images/about/pom-1.jpg"
                unoptimized
                alt="床にちょこんと座って舌を出して笑う、白い小さな犬のポム"
                width={1200}
                height={815}
                className="h-full w-full rounded-lg object-cover"
              />
            </div>
            <Image
              src="/images/about/pom-2.jpg"
              unoptimized
              alt="ベッドのそばでこちらを見上げるポム"
              width={1200}
              height={815}
              className="aspect-[3/2] w-full rounded-lg object-cover"
            />
            <Image
              src="/images/about/pom-3.jpg"
              unoptimized
              alt="夜の散歩中、立ち止まって振り返るポム"
              width={1200}
              height={815}
              className="aspect-[3/2] w-full rounded-lg object-cover"
            />
          </div>
          <figcaption className="text-sm text-gray-500 mt-2">ポム</figcaption>
        </figure>

        <p className="mt-4">
          <strong>コーラルの円は、犬のポムです。</strong>
          ポムは私が通っていた専門学校で生まれ、トリミング実習では練習台として学生たちの学びを支えていました。
          学校の里親制度を通じて4歳のときに迎え、その後5年を一緒に過ごしました。
          小柄で感情表現がはっきりしていて、同居していたビリーにもちょっかいを出して遊んでもらう子でした。
          9歳で亡くなりました。
        </p>

        <figure className="not-prose m-0 mt-8">
          <div className="grid grid-cols-2 gap-2">
            <Image
              src="/images/about/billy-1.jpg"
              unoptimized
              alt="両手でほっぺを包まれて、されるがままのビリー"
              width={1200}
              height={815}
              className="aspect-[3/2] w-full rounded-lg object-cover"
            />
            <Image
              src="/images/about/billy-2.jpg"
              unoptimized
              alt="布団の上でくつろぐ、白地に黒ぶちの大きな猫のビリー"
              width={1200}
              height={815}
              className="aspect-[3/2] w-full rounded-lg object-cover"
            />
            <Image
              src="/images/about/billy-3.jpg"
              unoptimized
              alt="気持ちよさそうに眠るビリー"
              width={1200}
              height={815}
              className="aspect-[3/2] w-full rounded-lg object-cover"
            />
            <Image
              src="/images/about/billy-4.jpg"
              unoptimized
              alt="ベランダから外を眺めるビリーの後ろ姿"
              width={1200}
              height={815}
              className="aspect-[3/2] w-full rounded-lg object-cover"
            />
          </div>
          <figcaption className="text-sm text-gray-500 mt-2">ビリー</figcaption>
        </figure>

        <p className="mt-4">
          <strong>ブルーグリーンの円は、猫のビリーです。</strong>
          ビリーは私が働いていた動物病院の近くで兄弟猫と一緒に拾われ、兄弟は先に引き取られましたが、ビリーだけが残りました。
          その後は病院猫として過ごし、体が大きかったこともあって、血液が必要な子のために輸血ドナーを務めていました。
          輸血のたびに麻酔の影響でふらつく姿を見て、引き取ることを決めました。
          家ではおとなしく、ポムのちょっかいにも静かに付き合ってくれる子でした。
          5年を一緒に過ごし、リンパ腫で9歳のとき亡くなりました。
        </p>
        <p className="mt-3">
          <strong>ふたつの円が重なる場所に、oneco の出発点があります。</strong>
          ポムは練習台として学生の学びに関わり、ビリーは輸血ドナーとして病院で過ごしました。
          2匹を見送るとき、行き場を探している子たちがポムやビリーのように誰かの家族になれるようにする、と約束しました。
          oneco という名前は、その約束に由来しています。
        </p>
      </section>

      <section className="mb-10">
        <h2 className="text-xl font-semibold mb-3">活動の目的</h2>
        <p>
          <strong>殺処分ゼロに近づける</strong> ことを目指しています。
        </p>
        <p className="mt-3">
          そのために、保護動物の存在を必要とする人に届ける役割を担います。
        </p>
        <ul className="list-disc ml-6 mt-3 space-y-1">
          <li>
            <strong>里親候補</strong> が、住んでいる地域や近隣の保護犬・保護猫を簡単に見つけられるようにする
          </li>
          <li>
            <strong>迷子のペットの飼い主</strong> が、自治体に収容されている可能性のある子を素早く発見できるようにする
          </li>
          <li>
            <strong>動物保護に関心がある方</strong> が、各地域の状況を俯瞰できる集計データを提供する
          </li>
        </ul>
      </section>

      <section className="mb-10">
        <h2 className="text-xl font-semibold mb-3">特徴</h2>
        <ul className="list-disc ml-6 space-y-2">
          <li>
            <strong>無料・広告なし</strong>:
            完全に非営利での運営。広告・有料機能は提供していません。
          </li>
          <li>
            <strong>公式情報集約</strong>:
            各自治体の公式サイトから取得した情報のみを掲載し、
            動物詳細ページには必ず元の自治体公式ページへのリンクを併記します。
          </li>
          <li>
            <strong>都道府県横断検索</strong>:
            複数自治体を跨いで犬種・性別・地域で絞り込めます。
          </li>
          <li>
            <strong>お気に入り機能</strong>:
            気になる子を保存して後から見直せます（ローカル保存のみ）。
          </li>
          <li>
            <strong>スマートフォン最適化</strong>:
            外出先からも快適にご利用いただけます。
          </li>
        </ul>
      </section>

      <section className="mb-10">
        <h2 className="text-xl font-semibold mb-3">データソースと運営方針</h2>
        <p>
          掲載情報はすべて、各自治体の公式サイトから収集した公開情報です。
          各自治体の <code>robots.txt</code> を尊重し、十分な間隔を空けて取得しています。
        </p>
        <p className="mt-3">
          詳細な運営方針・全データソースの一覧・著作権スタンス・撤去依頼の窓口については、
          <Link
            href="/transparency"
            className="text-[var(--color-primary-700)] hover:underline mx-1"
          >
            運営方針・撤去依頼ページ
          </Link>
          をご覧ください。
        </p>
      </section>

      <section className="mb-10">
        <h2 className="text-xl font-semibold mb-3">運営者</h2>
        <p>
          個人運営のプロジェクトです。
          技術的な詳細・進捗は
          <a
            href="https://github.com/9mak/oneco"
            target="_blank"
            rel="noopener noreferrer"
            className="text-[var(--color-primary-700)] hover:underline mx-1"
          >
            GitHub リポジトリ
          </a>
          にて公開しています。
        </p>
      </section>

      <section className="mb-10">
        <h2 className="text-xl font-semibold mb-3">お問い合わせ・ご意見</h2>
        <p>
          ご意見・ご提案・撤去依頼などは、
          <a
            href="https://github.com/9mak/oneco/issues"
            target="_blank"
            rel="noopener noreferrer"
            className="text-[var(--color-primary-700)] hover:underline mx-1"
          >
            GitHub Issues
          </a>
          までお寄せください。
        </p>
        <p className="mt-3">
          撤去依頼については
          <Link
            href="/transparency"
            className="text-[var(--color-primary-700)] hover:underline mx-1"
          >
            運営方針・撤去依頼ページ
          </Link>
          に専用フォームを用意しています（7 営業日以内の対応 SLA を明示）。
        </p>
      </section>

      <section>
        <h2 className="text-xl font-semibold mb-3">関連ページ</h2>
        <ul className="list-disc ml-6 space-y-1">
          <li><Link href="/transparency" className="text-[var(--color-primary-700)] hover:underline">運営方針・データソース・撤去依頼</Link></li>
          <li><Link href="/privacy" className="text-[var(--color-primary-700)] hover:underline">プライバシーポリシー</Link></li>
          <li><Link href="/terms" className="text-[var(--color-primary-700)] hover:underline">利用規約</Link></li>
        </ul>
      </section>
    </article>
  );
}
