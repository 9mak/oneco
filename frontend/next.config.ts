import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* 外部画像URL最適化設定
   * Codex リリースレビュー I-2 で指摘:
   * 全 https 許可は『任意URLの画像を自前ドメインで再配信する SSRF / 著作権露出』の
   * 構造になっていたため、sites.yaml の host を明示列挙する方式に変更。
   * scripts/deployment/setup_gcp.sh と同じく、新規サイト追加時はここも更新する。
   */
  images: {
    remotePatterns: [
      // sites.yaml から自動生成 (91 hosts)。
      // 生成コマンド:
      //   grep 'list_url:' src/data_collector/config/sites.yaml \
      //     | sed -E 's|.*https?://([^/"]+).*|\1|' | sort -u
      { protocol: 'https', hostname: 'animal-net.pref.nagasaki.jp' },
      { protocol: 'https', hostname: 'aniwel.jp' },
      { protocol: 'https', hostname: 'douai-tokushima.com' },
      { protocol: 'https', hostname: 'hyogo-douai.sakura.ne.jp' },
      { protocol: 'https', hostname: 'kochi-apc.com' },
      { protocol: 'https', hostname: 'kyoto-ani-love.com' },
      { protocol: 'https', hostname: 'mie-dakc.server-shared.com' },
      { protocol: 'https', hostname: 'nyantomo.jp' },
      { protocol: 'https', hostname: 'oita-aigo.com' },
      { protocol: 'https', hostname: 'shuyojoho.metro.tokyo.lg.jp' },
      { protocol: 'https', hostname: 'toyohashi-aikuru.jp' },
      { protocol: 'https', hostname: 'wannyan-navi.pref.aichi.jp' },
      { protocol: 'https', hostname: 'wannyapia.akita.jp' },
      { protocol: 'https', hostname: 'www.aniwel-pref.okinawa' },
      { protocol: 'https', hostname: 'www.aomori-animal.jp' },
      { protocol: 'https', hostname: 'www.city.akashi.lg.jp' },
      { protocol: 'https', hostname: 'www.city.amagasaki.hyogo.jp' },
      { protocol: 'https', hostname: 'www.city.chiba.jp' },
      { protocol: 'https', hostname: 'www.city.fukuyama.hiroshima.jp' },
      { protocol: 'https', hostname: 'www.city.funabashi.lg.jp' },
      { protocol: 'https', hostname: 'www.city.higashiosaka.lg.jp' },
      { protocol: 'https', hostname: 'www.city.hirakata.osaka.jp' },
      { protocol: 'https', hostname: 'www.city.hiroshima.lg.jp' },
      { protocol: 'https', hostname: 'www.city.kagoshima.lg.jp' },
      { protocol: 'https', hostname: 'www.city.kashiwa.lg.jp' },
      { protocol: 'https', hostname: 'www.city.kawasaki.jp' },
      { protocol: 'https', hostname: 'www.city.kitakyushu.lg.jp' },
      { protocol: 'https', hostname: 'www.city.kobe.lg.jp' },
      { protocol: 'https', hostname: 'www.city.koshigaya.saitama.jp' },
      { protocol: 'https', hostname: 'www.city.kumamoto.jp' },
      { protocol: 'https', hostname: 'www.city.kurashiki.okayama.jp' },
      { protocol: 'https', hostname: 'www.city.machida.tokyo.jp' },
      { protocol: 'https', hostname: 'www.city.maebashi.gunma.jp' },
      { protocol: 'https', hostname: 'www.city.matsuyama.ehime.jp' },
      { protocol: 'https', hostname: 'www.city.mito.lg.jp' },
      { protocol: 'https', hostname: 'www.city.miyazaki.miyazaki.jp' },
      { protocol: 'https', hostname: 'www.city.nagasaki.lg.jp' },
      { protocol: 'https', hostname: 'www.city.nagoya.jp' },
      { protocol: 'https', hostname: 'www.city.naha.okinawa.jp' },
      { protocol: 'https', hostname: 'www.city.nara.lg.jp' },
      { protocol: 'https', hostname: 'www.city.oita.oita.jp' },
      { protocol: 'https', hostname: 'www.city.okayama.jp' },
      { protocol: 'https', hostname: 'www.city.okazaki.lg.jp' },
      { protocol: 'https', hostname: 'www.city.osaka.lg.jp' },
      { protocol: 'https', hostname: 'www.city.otsu.lg.jp' },
      { protocol: 'https', hostname: 'www.city.saitama.lg.jp' },
      { protocol: 'https', hostname: 'www.city.sapporo.jp' },
      { protocol: 'https', hostname: 'www.city.sasebo.lg.jp' },
      { protocol: 'https', hostname: 'www.city.sendai.jp' },
      { protocol: 'https', hostname: 'www.city.takamatsu.kagawa.jp' },
      { protocol: 'https', hostname: 'www.city.takatsuki.osaka.jp' },
      { protocol: 'https', hostname: 'www.city.toyonaka.osaka.jp' },
      { protocol: 'https', hostname: 'www.city.toyota.aichi.jp' },
      { protocol: 'https', hostname: 'www.city.utsunomiya.lg.jp' },
      { protocol: 'https', hostname: 'www.city.wakayama.wakayama.jp' },
      { protocol: 'https', hostname: 'www.city.yokkaichi.lg.jp' },
      { protocol: 'https', hostname: 'www.city.yokohama.lg.jp' },
      { protocol: 'https', hostname: 'www.douai.pref.tochigi.lg.jp' },
      { protocol: 'https', hostname: 'www.douaicenter.jp' },
      { protocol: 'https', hostname: 'www.hama-aikyou.jp' },
      { protocol: 'https', hostname: 'www.kumamoto-doubutuaigo.jp' },
      { protocol: 'https', hostname: 'www.pref.chiba.lg.jp' },
      { protocol: 'https', hostname: 'www.pref.ehime.jp' },
      { protocol: 'https', hostname: 'www.pref.fukui.lg.jp' },
      { protocol: 'https', hostname: 'www.pref.fukushima.lg.jp' },
      { protocol: 'https', hostname: 'www.pref.gifu.lg.jp' },
      { protocol: 'https', hostname: 'www.pref.gunma.jp' },
      { protocol: 'https', hostname: 'www.pref.hiroshima.lg.jp' },
      { protocol: 'https', hostname: 'www.pref.ibaraki.jp' },
      { protocol: 'https', hostname: 'www.pref.ishikawa.lg.jp' },
      { protocol: 'https', hostname: 'www.pref.iwate.jp' },
      { protocol: 'https', hostname: 'www.pref.kagawa.lg.jp' },
      { protocol: 'https', hostname: 'www.pref.kanagawa.jp' },
      { protocol: 'https', hostname: 'www.pref.kyoto.jp' },
      { protocol: 'https', hostname: 'www.pref.nagano.lg.jp' },
      { protocol: 'https', hostname: 'www.pref.niigata.lg.jp' },
      { protocol: 'https', hostname: 'www.pref.okayama.jp' },
      { protocol: 'https', hostname: 'www.pref.osaka.lg.jp' },
      { protocol: 'https', hostname: 'www.pref.saga.lg.jp' },
      { protocol: 'https', hostname: 'www.pref.shimane.lg.jp' },
      { protocol: 'https', hostname: 'www.pref.shizuoka.jp' },
      { protocol: 'https', hostname: 'www.pref.tottori.lg.jp' },
      { protocol: 'https', hostname: 'www.pref.toyama.jp' },
      { protocol: 'https', hostname: 'www.pref.wakayama.lg.jp' },
      { protocol: 'https', hostname: 'www.pref.yamagata.jp' },
      { protocol: 'https', hostname: 'www.pref.yamaguchi.lg.jp' },
      { protocol: 'https', hostname: 'www.pref.yamanashi.jp' },
      { protocol: 'https', hostname: 'www.sapca.jp' },
      { protocol: 'https', hostname: 'www.wannyan.city.fukuoka.lg.jp' },
      { protocol: 'https', hostname: 'www.yokosuka-doubutu.com' },
      { protocol: 'https', hostname: 'www.zaidan-fukuoka-douai.or.jp' },
    ],
    formats: ['image/webp', 'image/avif'], // WebP/AVIF自動変換
    /* 著作権配慮（著作権法47条の5「軽微利用」の趣旨）:
     * 元サイト画像をそのまま再配信せず、検索・所在案内に必要な範囲の
     * 縮小サムネイルに留める。配信解像度の上限と品質を抑える。
     */
    deviceSizes: [640, 750, 828],
    imageSizes: [96, 128, 256, 384],
    qualities: [60],
  },

  /* Content Security Policy ヘッダー設定
   * img-src は 209+ 自治体サイトすべての画像を許可するため `https:` 全許可。
   * 同様の理由で個別ドメイン列挙は非現実的。
   */
  async headers() {
    // dev は React Refresh / Fast Refresh で eval が必要、本番は除去して
    // XSS の爆発半径を縮める (R-3: Codex リリースレビュー指摘)。
    const isDev = process.env.NODE_ENV !== 'production';
    const scriptSrc = isDev
      ? "script-src 'self' 'unsafe-inline' 'unsafe-eval'"
      : "script-src 'self' 'unsafe-inline'";
    return [
      {
        source: '/:path*',
        headers: [
          {
            key: 'Content-Security-Policy',
            value: [
              "default-src 'self'",
              scriptSrc,
              "style-src 'self' 'unsafe-inline'",
              "img-src 'self' data: https:",
              `connect-src 'self' ${process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'}`,
            ].join('; '),
          },
        ],
      },
    ];
  },
};

export default nextConfig;
