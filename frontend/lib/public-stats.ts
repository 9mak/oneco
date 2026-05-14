export interface PublicStats {
  total_animals: number;
  municipality_count: number;
  site_count: number;
  avg_waiting_days: number | null;
}

export class PublicStatsError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
  ) {
    super(message);
    this.name = 'PublicStatsError';
  }
}

/**
 * 公開メトリクス API `/public/stats` を取得する。認証不要、CORS 開放。
 *
 * Server Component / Route Handler どちらからでも呼び出し可能。
 * SSG / ISR を念頭に置き revalidate オプションで再検証間隔を指定できる。
 */
export async function fetchPublicStats(
  options: { revalidateSec?: number } = {},
): Promise<PublicStats> {
  const baseUrl =
    process.env.BACKEND_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL;
  if (!baseUrl) {
    throw new PublicStatsError(
      'BACKEND_INTERNAL_URL or NEXT_PUBLIC_API_BASE_URL must be set',
    );
  }

  const revalidate = options.revalidateSec ?? 300;
  const res = await fetch(`${baseUrl}/public/stats`, {
    next: { revalidate },
  });
  if (!res.ok) {
    throw new PublicStatsError(
      `Failed to fetch public stats: ${res.status}`,
      res.status,
    );
  }
  return res.json();
}
