import type { Metadata } from 'next';

// お気に入りは localStorage ベースの個人ページで固有の公開コンテンツが無く、
// page.tsx が 'use client' のため metadata を持てない。layout で noindex を付与し、
// 同時に layout.tsx の既定 canonical '/' を打ち消す (ホーム重複申告の回避)。
export const metadata: Metadata = {
  robots: { index: false, follow: true },
};

export default function FavoritesLayout({ children }: { children: React.ReactNode }) {
  return children;
}
