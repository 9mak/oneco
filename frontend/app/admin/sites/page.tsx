import Link from 'next/link';
import { AdminStatsError, fetchAdminSites } from '@/lib/admin';

export const metadata = {
  title: 'サイト健全性 | oneco',
  robots: { index: false, follow: false },
};

const STATUS_LABEL: Record<'ok' | 'warning' | 'failing', string> = {
  ok: '正常',
  warning: '失敗あり',
  failing: '連続失敗 (auto-skip 中)',
};

const STATUS_COLOR: Record<'ok' | 'warning' | 'failing', string> = {
  ok: 'bg-green-100 text-green-800',
  warning: 'bg-yellow-100 text-yellow-800',
  failing: 'bg-red-100 text-red-800',
};

function formatDate(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleString('ja-JP', { timeZone: 'Asia/Tokyo' });
}

function truncate(text: string | null, max: number): string {
  if (!text) return '—';
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

export default async function AdminSitesPage() {
  let data: Awaited<ReturnType<typeof fetchAdminSites>> | null = null;
  let error: string | null = null;

  try {
    data = await fetchAdminSites();
  } catch (e) {
    error =
      e instanceof AdminStatsError ? e.message : 'サイト一覧の取得に失敗しました';
  }

  return (
    <main className="mx-auto max-w-7xl px-4 py-8">
      <header className="mb-6 flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl font-bold">サイト健全性</h1>
          <p className="text-sm text-gray-600">
            209+ サイトの収集ステータスと最終失敗エラー
            {data && `（生成: ${formatDate(data.generated_at)}）`}
          </p>
        </div>
        <Link
          href="/admin"
          className="rounded border border-gray-300 px-3 py-1 text-sm hover:bg-gray-50"
        >
          ← ダッシュボードへ戻る
        </Link>
      </header>

      {error && (
        <div
          role="alert"
          className="mb-6 rounded border border-red-300 bg-red-50 p-4 text-red-800"
        >
          {error}
        </div>
      )}

      {data && (
        <>
          <section className="mb-6 grid gap-4 md:grid-cols-4">
            <SummaryCard label="全サイト" value={data.total} />
            <SummaryCard
              label="正常"
              value={data.summary.ok}
              tone="ok"
            />
            <SummaryCard
              label="失敗あり"
              value={data.summary.warning}
              tone="warning"
            />
            <SummaryCard
              label="auto-skip 中"
              value={data.summary.failing}
              tone="failing"
            />
          </section>

          <section className="overflow-x-auto rounded border border-gray-200 bg-white">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-left">
                <tr>
                  <th className="px-3 py-2 font-medium">状態</th>
                  <th className="px-3 py-2 font-medium">サイト</th>
                  <th className="px-3 py-2 font-medium">都道府県</th>
                  <th className="px-3 py-2 text-right font-medium">DB件数</th>
                  <th className="px-3 py-2 text-right font-medium">連続失敗</th>
                  <th className="px-3 py-2 font-medium">最終失敗</th>
                  <th className="px-3 py-2 font-medium">エラー (抜粋)</th>
                </tr>
              </thead>
              <tbody>
                {[...data.sites]
                  .sort((a, b) => {
                    const order = { failing: 0, warning: 1, ok: 2 };
                    if (a.health.status !== b.health.status) {
                      return order[a.health.status] - order[b.health.status];
                    }
                    return a.name.localeCompare(b.name, 'ja');
                  })
                  .map((site) => (
                    <tr key={site.name} className="border-t border-gray-200 align-top">
                      <td className="px-3 py-2">
                        <span
                          className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${STATUS_COLOR[site.health.status]}`}
                        >
                          {STATUS_LABEL[site.health.status]}
                        </span>
                      </td>
                      <td className="px-3 py-2">
                        <div className="font-medium">{site.name}</div>
                        <a
                          href={site.list_url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-xs text-blue-600 hover:underline"
                        >
                          {site.host}
                        </a>
                      </td>
                      <td className="px-3 py-2">{site.prefecture}</td>
                      <td className="px-3 py-2 text-right tabular-nums">
                        {site.db_count}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums">
                        {site.health.consecutive_failures}
                      </td>
                      <td className="px-3 py-2 whitespace-nowrap">
                        {formatDate(site.health.last_failed_at)}
                      </td>
                      <td className="px-3 py-2 text-xs text-gray-600">
                        {truncate(site.health.last_error, 120)}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </section>
        </>
      )}
    </main>
  );
}

function SummaryCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone?: 'ok' | 'warning' | 'failing';
}) {
  const toneClass =
    tone === 'ok'
      ? 'border-green-300 bg-green-50'
      : tone === 'warning'
        ? 'border-yellow-300 bg-yellow-50'
        : tone === 'failing'
          ? 'border-red-300 bg-red-50'
          : 'border-gray-200 bg-white';
  return (
    <div className={`rounded border p-4 shadow-sm ${toneClass}`}>
      <div className="text-sm text-gray-600">{label}</div>
      <div className="mt-1 text-3xl font-bold tabular-nums">{value}</div>
    </div>
  );
}
