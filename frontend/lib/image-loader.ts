import type { ImageLoaderProps } from 'next/image';

/**
 * next/image のカスタム loader。
 *
 * Vercel の画像最適化 (/_next/image) は Hobby プランの変換クォータを使い切ると
 * 402 を返し、全動物サムネイルが表示されなくなる (2026-07-07 本番障害)。
 * 動物は日次で増えるため無料枠内には収まらず、恒常的に再発する構造だった。
 *
 * 代わりに wsrv.nl (無料・CDNキャッシュ付きの画像プロキシ) で縮小・WebP 変換する。
 * 「元画像をそのまま再配信せず縮小サムネイルに留める」という著作権配慮
 * (著作権法47条の5 の軽微利用、next.config.ts の images コメント参照) は維持される。
 */
export default function imageLoader({ src, width, quality }: ImageLoaderProps): string {
  // ローカル静的アセット (/images/... 等) は変換せずそのまま配信する
  if (src.startsWith('/')) {
    return src;
  }
  const params = new URLSearchParams({
    url: src,
    w: String(width),
    q: String(quality ?? 60),
    output: 'webp',
    we: '1', // without enlargement: 元画像より拡大しない
  });
  return `https://wsrv.nl/?${params.toString()}`;
}
