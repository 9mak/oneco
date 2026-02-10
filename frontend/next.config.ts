import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* 外部画像URL最適化設定 */
  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: '**.kochi-apc.com', // 高知県動物愛護センター
        pathname: '/images/**',
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
            value: "default-src 'self'; img-src 'self' https://*.kochi-apc.com; script-src 'self' 'unsafe-inline' 'unsafe-eval';",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
