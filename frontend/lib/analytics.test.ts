import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

const sendGAEventMock = vi.fn();
vi.mock('@next/third-parties/google', () => ({
  sendGAEvent: (...args: unknown[]) => sendGAEventMock(...args),
}));

const originalEnv = { ...process.env };

async function reload() {
  vi.resetModules();
  return await import('./analytics');
}

describe('analytics', () => {
  beforeEach(() => {
    process.env = { ...originalEnv };
    sendGAEventMock.mockReset();
  });

  afterEach(() => {
    process.env = { ...originalEnv };
  });

  it('GA Measurement ID 未設定なら sendGAEvent を呼ばない', async () => {
    delete process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID;
    const { trackExternalLinkClick } = await reload();
    trackExternalLinkClick({ linkUrl: 'https://example.gov' });
    expect(sendGAEventMock).not.toHaveBeenCalled();
  });

  it('Measurement ID 設定済みなら external_link_click を sendGAEvent に渡す', async () => {
    process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID = 'G-TEST';
    const { trackExternalLinkClick } = await reload();
    trackExternalLinkClick({
      linkUrl: 'https://example.gov/animals/1',
      prefecture: '高知県',
      animalId: 'abc',
    });
    expect(sendGAEventMock).toHaveBeenCalledWith('event', 'external_link_click', {
      link_url: 'https://example.gov/animals/1',
      prefecture: '高知県',
      animal_id: 'abc',
    });
  });

  it('undefined パラメータは送信ペイロードから除外する', async () => {
    process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID = 'G-TEST';
    const { trackExternalLinkClick } = await reload();
    trackExternalLinkClick({ linkUrl: 'https://example.gov' });
    expect(sendGAEventMock).toHaveBeenCalledWith('event', 'external_link_click', {
      link_url: 'https://example.gov',
    });
  });

  it('search_used は query_length / has_results を送る (本文は送らない)', async () => {
    process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID = 'G-TEST';
    const { trackSearchUsed } = await reload();
    trackSearchUsed({ queryLength: 5, hasResults: true });
    expect(sendGAEventMock).toHaveBeenCalledWith('event', 'search_used', {
      query_length: 5,
      has_results: true,
    });
  });

  it('sendGAEvent が throw しても黙殺する (UX を壊さない)', async () => {
    process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID = 'G-TEST';
    sendGAEventMock.mockImplementation(() => {
      throw new Error('GA down');
    });
    const { trackExternalLinkClick } = await reload();
    expect(() =>
      trackExternalLinkClick({ linkUrl: 'https://example.gov' }),
    ).not.toThrow();
  });
});
