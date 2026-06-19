import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { GoogleAnalytics } from "@next/third-parties/google";
import "./globals.css";
import { Header } from "@/components/layout/Header";
import { Footer } from "@/components/layout/Footer";
import { OrganizationSchema } from "@/components/animals/PetSchema";
import { getSiteUrl } from "@/lib/site-url";

// GA4 Measurement ID (G-XXXXXXXXXX 形式)。
// 未設定 (preview/local 等) では GA4 を埋め込まない設計。
// 本番のみ Vercel 環境変数 NEXT_PUBLIC_GA_MEASUREMENT_ID で注入する。
const GA_MEASUREMENT_ID = process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID;

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const SITE_URL = getSiteUrl();
const SITE_NAME = 'oneco';
const SITE_DESCRIPTION =
  '全国の自治体に保護されている犬・猫の情報を一元化したポータルサイト。譲渡対象動物・迷子情報を都道府県別・条件別に検索できます。';

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: SITE_NAME,
    template: `%s | ${SITE_NAME}`,
  },
  description: SITE_DESCRIPTION,
  applicationName: SITE_NAME,
  keywords: ['保護動物', '譲渡', '里親', '迷子', '犬', '猫', '動物愛護センター', 'ペット'],
  authors: [{ name: 'oneco' }],
  alternates: {
    canonical: '/',
  },
  openGraph: {
    type: 'website',
    locale: 'ja_JP',
    url: SITE_URL,
    siteName: SITE_NAME,
    title: SITE_NAME,
    description: SITE_DESCRIPTION,
  },
  twitter: {
    card: 'summary_large_image',
    title: SITE_NAME,
    description: SITE_DESCRIPTION,
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      'max-image-preview': 'large',
      'max-snippet': -1,
    },
  },
  // Google Search Console 所有権確認用メタタグ。
  // Search Console 経由で 2026-06-12 に発行された値を恒久的に <head> に出力する。
  // 確認状態維持のためタグを削除しないこと (Search Console は再確認時にも参照する)。
  verification: {
    google: 'ufKu9iul0LIV0gySiea-ULneLToLgFil3dgBtS2Icjs',
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ja">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        <OrganizationSchema siteUrl={SITE_URL} siteName={SITE_NAME} />
        {/* スキップリンク (WCAG 2.4.1 Bypass Blocks): フォーカス時のみ可視化 */}
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[100] focus:rounded-md focus:bg-white focus:px-4 focus:py-2 focus:text-[var(--color-primary-700)] focus:shadow-md focus:outline-none focus:ring-2 focus:ring-[var(--color-focus-ring)]"
        >
          本文へ移動
        </a>
        <div className="flex flex-col min-h-screen">
          <Header />
          <main id="main" className="flex-1">
            {children}
          </main>
          <Footer />
        </div>
      </body>
      {GA_MEASUREMENT_ID && <GoogleAnalytics gaId={GA_MEASUREMENT_ID} />}
    </html>
  );
}
