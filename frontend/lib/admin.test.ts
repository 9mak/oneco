import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { AdminStatsError, fetchAdminStats } from './admin';

const originalEnv = { ...process.env };
const originalFetch = global.fetch;

const SAMPLE_STATS = {
  total_animals: 10,
  by_status: { sheltered: 8, adopted: 2, returned: 0, deceased: 0 },
  by_prefecture: [{ prefecture: '高知県', count: 5 }],
  by_species: { 犬: 6, 猫: 4 },
  by_category: { adoption: 9, lost: 1 },
  image_hash_summary: { total: 100, oldest: '2026-01-01T00:00:00Z', newest: '2026-05-01T00:00:00Z' },
  quality: {
    prefectures_covered: 1,
    prefectures_total: 47,
    field_missing_ratio: { prefecture: 0, image_urls: 0.1 },
    added_in_last_7days: 3,
  },
  site_coverage: {
    sites_total: 209,
    sites_with_data: 5,
    sites_without_data: 204,
  },
  last_shelter_date: '2026-05-09',
  generated_at: '2026-05-08T00:00:00Z',
};

describe('fetchAdminStats', () => {
  beforeEach(() => {
    process.env = { ...originalEnv };
    process.env.BACKEND_INTERNAL_URL = 'http://backend.test';
    process.env.INTERNAL_API_TOKEN = 'tok-123';
  });

  afterEach(() => {
    process.env = { ...originalEnv };
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('returns parsed stats when backend responds 200', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(SAMPLE_STATS), { status: 200 }),
    );
    global.fetch = fetchSpy as unknown as typeof fetch;

    const stats = await fetchAdminStats();

    expect(stats.total_animals).toBe(10);
    expect(fetchSpy).toHaveBeenCalledWith(
      'http://backend.test/admin/stats',
      expect.objectContaining({
        headers: { 'X-Internal-Token': 'tok-123' },
        cache: 'no-store',
      }),
    );
  });

  it('throws AdminStatsError when token is missing', async () => {
    delete process.env.INTERNAL_API_TOKEN;

    await expect(fetchAdminStats()).rejects.toThrow(AdminStatsError);
    await expect(fetchAdminStats()).rejects.toThrow(/INTERNAL_API_TOKEN/);
  });

  it('throws AdminStatsError when base URL is missing', async () => {
    delete process.env.BACKEND_INTERNAL_URL;
    delete process.env.NEXT_PUBLIC_API_BASE_URL;

    await expect(fetchAdminStats()).rejects.toThrow(AdminStatsError);
    await expect(fetchAdminStats()).rejects.toThrow(/BACKEND_INTERNAL_URL/);
  });

  it('falls back to NEXT_PUBLIC_API_BASE_URL if BACKEND_INTERNAL_URL is unset', async () => {
    delete process.env.BACKEND_INTERNAL_URL;
    process.env.NEXT_PUBLIC_API_BASE_URL = 'http://public.test';

    const fetchSpy = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(SAMPLE_STATS), { status: 200 }),
    );
    global.fetch = fetchSpy as unknown as typeof fetch;

    await fetchAdminStats();

    expect(fetchSpy).toHaveBeenCalledWith(
      'http://public.test/admin/stats',
      expect.anything(),
    );
  });

  it('throws AdminStatsError with status when backend returns non-200', async () => {
    global.fetch = vi.fn().mockResolvedValue(new Response('', { status: 401 })) as unknown as typeof fetch;

    try {
      await fetchAdminStats();
      expect.fail('should have thrown');
    } catch (e) {
      expect(e).toBeInstanceOf(AdminStatsError);
      expect((e as AdminStatsError).status).toBe(401);
    }
  });
});
