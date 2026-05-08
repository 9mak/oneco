import { auth } from '@/auth';
import { AdminStatsError, fetchAdminStats } from '@/lib/admin';
import Link from 'next/link';

export const metadata = {
  title: '管理ダッシュボード | oneco',
  robots: { index: false, follow: false },
};

const STATUS_LABELS: Record<string, string> = {
  sheltered: '収容中',
  adopted: '譲渡完了',
  returned: '飼い主返還',
  deceased: '死亡',
};

const CATEGORY_LABELS: Record<string, string> = {
  adoption: '譲渡対象',
  lost: '迷子',
  sheltered: '収容のみ',
};

const FIELD_LABELS: Record<string, string> = {
  prefecture: '都道府県',
  image_urls: '画像',
  color: '毛色',
  size: 'サイズ',
  phone: '電話番号',
  age_months: '年齢',
};

function formatDate(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleString('ja-JP', { timeZone: 'Asia/Tokyo' });
}

export default async function AdminDashboardPage() {
  const session = await auth();
  let stats: Awaited<ReturnType<typeof fetchAdminStats>> | null = null;
  let error: string | null = null;

  try {
    stats = await fetchAdminStats();
  } catch (e) {
    error =
      e instanceof AdminStatsError
        ? e.message
        : '集計データの取得に失敗しました';
  }

  return (
    <main className="mx-auto max-w-6xl px-4 py-8">
      <header className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">管理ダッシュボード</h1>
          <p className="text-sm text-gray-600">
            ログイン中: {session?.user?.email ?? session?.user?.name ?? '不明'}
            （集計時刻: {stats ? formatDate(stats.generated_at) : '—'}）
          </p>
        </div>
        <Link
          href="/api/auth/signout"
          className="rounded border border-gray-300 px-3 py-1 text-sm hover:bg-gray-50"
        >
          サインアウト
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

      {stats && (
        <div className="grid gap-6 md:grid-cols-2">
          <SummaryCard title="全件数" value={stats.total_animals} />
          <SummaryCard title="累積画像ハッシュ" value={stats.image_hash_summary.total} />
          <SummaryCard
            title="県カバー率"
            value={`${stats.quality.prefectures_covered} / ${stats.quality.prefectures_total}`}
          />
          <SummaryCard
            title="直近7日の収容"
            value={stats.quality.added_in_last_7days}
          />

          <Section title="フィールド欠損率">
            <DefList
              entries={Object.entries(stats.quality.field_missing_ratio).map(([k, v]) => [
                FIELD_LABELS[k] ?? k,
                `${(v * 100).toFixed(1)}%`,
              ])}
            />
          </Section>

          <Section title="(運用情報)">
            <p className="text-sm text-gray-600">
              欠損率が高いフィールドは抽出ロジックの改善対象。直近7日の収容が
              異常に少ない場合は GitHub Actions の Data Collector ワークフローを確認。
            </p>
          </Section>

          <Section title="ステータス別">
            <DefList
              entries={Object.entries(stats.by_status).map(([k, v]) => [
                STATUS_LABELS[k] ?? k,
                v,
              ])}
            />
          </Section>

          <Section title="カテゴリ別">
            <DefList
              entries={Object.entries(stats.by_category).map(([k, v]) => [
                CATEGORY_LABELS[k] ?? k,
                v,
              ])}
            />
          </Section>

          <Section title="種別">
            <DefList entries={Object.entries(stats.by_species)} />
          </Section>

          <Section title="画像ハッシュ収集期間">
            <DefList
              entries={[
                ['最古', formatDate(stats.image_hash_summary.oldest)],
                ['最新', formatDate(stats.image_hash_summary.newest)],
              ]}
            />
          </Section>

          <section className="md:col-span-2">
            <h2 className="mb-3 text-lg font-semibold">県別件数</h2>
            <div className="overflow-x-auto rounded border border-gray-200">
              <table className="w-full text-sm">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium">都道府県</th>
                    <th className="px-3 py-2 text-right font-medium">件数</th>
                  </tr>
                </thead>
                <tbody>
                  {stats.by_prefecture.map((row) => (
                    <tr key={row.prefecture} className="border-t border-gray-200">
                      <td className="px-3 py-2">{row.prefecture}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{row.count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      )}
    </main>
  );
}

function SummaryCard({ title, value }: { title: string; value: number | string }) {
  return (
    <div className="rounded border border-gray-200 bg-white p-4 shadow-sm">
      <div className="text-sm text-gray-600">{title}</div>
      <div className="mt-1 text-3xl font-bold tabular-nums">{value}</div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded border border-gray-200 bg-white p-4 shadow-sm">
      <h2 className="mb-3 text-lg font-semibold">{title}</h2>
      {children}
    </section>
  );
}

function DefList({ entries }: { entries: Array<[string, number | string]> }) {
  if (entries.length === 0) {
    return <p className="text-sm text-gray-500">データなし</p>;
  }
  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
      {entries.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-gray-600">{k}</dt>
          <dd className="text-right font-medium tabular-nums">{v}</dd>
        </div>
      ))}
    </dl>
  );
}
