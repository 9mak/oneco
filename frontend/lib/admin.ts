import 'server-only';

export interface AdminStats {
  total_animals: number;
  by_status: Record<string, number>;
  by_prefecture: Array<{ prefecture: string; count: number }>;
  by_species: Record<string, number>;
  by_category: Record<string, number>;
  image_hash_summary: {
    total: number;
    oldest: string | null;
    newest: string | null;
  };
  quality: {
    prefectures_covered: number;
    prefectures_total: number;
    field_missing_ratio: Record<string, number>;
    added_in_last_7days: number;
  };
  site_coverage: {
    sites_total: number;
    sites_with_data: number;
    sites_without_data: number;
  };
  last_shelter_date: string | null;
  generated_at: string;
}

export class AdminStatsError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
  ) {
    super(message);
    this.name = 'AdminStatsError';
  }
}

export async function fetchAdminStats(): Promise<AdminStats> {
  const baseUrl = process.env.BACKEND_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL;
  const token = process.env.INTERNAL_API_TOKEN;

  if (!baseUrl) {
    throw new AdminStatsError('BACKEND_INTERNAL_URL or NEXT_PUBLIC_API_BASE_URL must be set');
  }
  if (!token) {
    throw new AdminStatsError('INTERNAL_API_TOKEN is not set');
  }

  const res = await fetch(`${baseUrl}/admin/stats`, {
    headers: { 'X-Internal-Token': token },
    cache: 'no-store',
  });

  if (!res.ok) {
    throw new AdminStatsError(`Failed to fetch admin stats: ${res.status}`, res.status);
  }
  return res.json();
}
