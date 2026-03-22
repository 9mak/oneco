import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* 外部画像URL最適化設定 */
  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: 'kochi-apc.com', // 高知県中央・中村小動物管理センター
        pathname: '/**',
      },
      {
        protocol: 'https',
        hostname: '**.kochi-apc.com',
        pathname: '/**',
      },
      // 将来的に他の都道府県ドメインを追加
    ],
    formats: ['image/webp', 'image/avif'], // WebP/AVIF自動変換
  },

  /* Content Security Policy ヘッダー設定 */
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
              "img-src 'self' data: https://*.kochi-apc.com",
              `connect-src 'self' ${process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'}`,
            ].join('; '),
          },
        ],
      },
    ];
  },
};

export default nextConfig;
