import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* 外部画像URL最適化設定
   * 209+ 自治体サイトから収集する画像を Next.js Image で最適化するため、
   * 全 https ドメインを許可する。サイトを 1 件ずつ列挙するのは非現実的。
   * セキュリティリスクは Next.js 側で URL fetch + 画像形式バリデーションされる。
   */
  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: '**',
        pathname: '/**',
      },
    ],
    formats: ['image/webp', 'image/avif'], // WebP/AVIF自動変換
  },

  /* Content Security Policy ヘッダー設定
   * img-src は 209+ 自治体サイトすべての画像を許可するため `https:` 全許可。
   * 同様の理由で個別ドメイン列挙は非現実的。
   */
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          {
            key: 'Content-Security-Policy',
            value: [
              "default-src 'self'",
              "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
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
