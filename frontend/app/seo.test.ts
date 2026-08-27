import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('next/font/google', () => ({
  Geist: () => ({ variable: '--font-geist-sans', className: 'geist-sans' }),
  Geist_Mono: () => ({ variable: '--font-geist-mono', className: 'geist-mono' }),
}));

vi.mock('@next/third-parties/google', () => ({
  GoogleAnalytics: () => null,
}));

import { metadata as statsMetadata } from './stats/page';
import { metadata as rootMetadata } from './layout';

/**
 * 2026-06-16 のSEO監査で、(1) /stats が layout の既定 canonical '/' を継承して
 * ホーム重複扱いになる、(2) sitemap に静的コンテンツページが欠落、という2件を
 * 検出。再発防止のリグレッションテスト。
 */
describe('SEO: canonical 上書き', () => {
  it('/stats は自己URLを canonical に指定する (ホーム継承しない)', () => {
    expect(statsMetadata.alternates?.canonical).toBe('/stats');
  });
});

/**
 * 2026-08-26のSEO監査で、トップページの title デフォルト値が
 * ブランド名 "oneco" 単体のみで、非ブランド検索語（保護犬・保護猫・里親等）を
 * 含まず検索流入を取りこぼしている点を検出。再発防止のリグレッションテスト。
 */
describe('SEO: title デフォルト値の非ブランド検索語', () => {
  it('title.default はブランド名単体ではなく保護犬・保護猫・里親を含む', () => {
    const title = rootMetadata.title;
    const defaultTitle = typeof title === 'object' && title && 'default' in title ? title.default : undefined;
    expect(defaultTitle).toBeDefined();
    expect(defaultTitle).not.toBe('oneco');
    expect(defaultTitle).toMatch(/保護犬/);
    expect(defaultTitle).toMatch(/保護猫/);
    expect(defaultTitle).toMatch(/里親/);
  });
});

describe('SEO: sitemap 静的ページ列挙', () => {
  beforeEach(() => {
    // ビルド/テスト環境では API 不在。res.ok=false で動物 fetch を空にフォールバック。
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, json: async () => ({}) }),
    );
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('インデックス対象の静的コンテンツページを列挙する', async () => {
    const sitemap = (await import('./sitemap')).default;
    const routes = await sitemap();
    const urls = routes.map((r) => r.url);
    for (const path of ['/stats', '/about', '/transparency', '/archive']) {
      expect(urls.some((u) => u.endsWith(path))).toBe(true);
    }
  });
});
