import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { metadata as statsMetadata } from './stats/page';

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
