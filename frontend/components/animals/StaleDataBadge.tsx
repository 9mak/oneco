/**
 * StaleDataBadge Component
 * 収容日から経過日数を計算して、掲載が古い (30日/60日以上経過) ことを
 * ユーザーに視覚的に伝える。元サイトでの最新確認を促す UI セーフネット。
 *
 * Why: クローラの実行は1日1回のため、自治体側で削除/更新された動物情報が
 * 最大24時間遅延する。さらに自治体サイトの掲載期限切れ (告示期間終了等)
 * を見逃すケースもあり、古い情報を誤って参照させないためのバッジ。
 */

'use client';

interface StaleDataBadgeProps {
  /** 収容日 (YYYY-MM-DD 形式の文字列) */
  shelterDate: string;
}

const DAYS_STALE_WARN = 30;
const DAYS_STALE_STRONG = 60;
const MS_PER_DAY = 1000 * 60 * 60 * 24;

export function StaleDataBadge({ shelterDate }: StaleDataBadgeProps) {
  const shelter = new Date(shelterDate);
  if (Number.isNaN(shelter.getTime())) {
    return null;
  }
  const today = new Date();
  const diffDays = Math.floor((today.getTime() - shelter.getTime()) / MS_PER_DAY);

  // 未来日付や30日未満は表示しない
  if (diffDays < DAYS_STALE_WARN) {
    return null;
  }

  const threshold = diffDays >= DAYS_STALE_STRONG ? DAYS_STALE_STRONG : DAYS_STALE_WARN;
  const label = `掲載から${threshold}日以上経過`;
  const colorClass =
    diffDays >= DAYS_STALE_STRONG
      ? 'bg-orange-100 text-orange-800 border-orange-300'
      : 'bg-yellow-100 text-yellow-800 border-yellow-300';

  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium border rounded-full ${colorClass}`}
      role="status"
      aria-label={`${label} — 最新の掲載状況は元のサイトでご確認ください`}
      title="最新の掲載状況は元のサイトでご確認ください"
    >
      <svg
        className="w-3 h-3"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
        />
      </svg>
      {label}
    </span>
  );
}
