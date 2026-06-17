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
      // Next.js 16 から remotePatterns は最大 50 件の制約。sites.yaml は 211
      // サイト / 91 host で個別列挙だと上限超過 (Build error)。
      // 設計判断: 日本国内ドメイン (.jp / .okinawa) と特定の動物愛護センター系
      // .com に限定。.jp/.okinawa は JPRS / レジストラ管理で第三者の悪意ある
      // 大量取得が困難。当初の I-2 で懸念した「任意 https 許可」よりは大幅に
      // 狭く、Next.js の上限内に収まる現実的な範囲。
      // 新しい host を追加するときは sites.yaml の host を確認し、TLD が
      // .jp/.okinawa 以外なら下の例外リストに追加する。
      { protocol: 'https', hostname: '**.jp' },
      { protocol: 'https', hostname: '**.okinawa' },
      // .com / 特殊 TLD の例外列挙 (sites.yaml に新規追加時はここも更新)。
      // 2026-06-11 監査: sites.yaml 全 91 host のうち .jp/.okinawa 以外は 6 host。
      // 列挙漏れがあると画像最適化が失敗し /_next/image でその host の画像が
      // 表示不可になる (実害)。yaml と一致しているか定期確認すること。
      { protocol: 'https', hostname: 'douai-tokushima.com' },
      { protocol: 'https', hostname: 'kochi-apc.com' },
      { protocol: 'https', hostname: 'kyoto-ani-love.com' },
      { protocol: 'https', hostname: 'oita-aigo.com' },
      { protocol: 'https', hostname: 'mie-dakc.server-shared.com' },
      { protocol: 'https', hostname: 'www.yokosuka-doubutu.com' },
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
    // GA4 / Google Tag Manager。@next/third-parties の <GoogleAnalytics> が
    // googletagmanager.com から gtag を読み込み、計測ビーコンを
    // google-analytics.com (リージョン別サブドメイン含む) へ送る。
    // これらを許可しないと CSP がスクリプト読込とビーコン送信の両方を
    // ブロックし、計測が完全に死ぬ (2026-06-15 本番で発覚)。
    const gtm = 'https://www.googletagmanager.com';
    const gaConnect = 'https://www.google-analytics.com https://*.google-analytics.com';
    const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';
    const scriptSrc = isDev
      ? `script-src 'self' 'unsafe-inline' 'unsafe-eval' ${gtm}`
      : `script-src 'self' 'unsafe-inline' ${gtm}`;
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
              `connect-src 'self' ${apiBase} ${gtm} ${gaConnect}`,
            ].join('; '),
          },
        ],
      },
    ];
  },
};

export default nextConfig;
