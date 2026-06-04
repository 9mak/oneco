import Link from 'next/link';

interface PrefectureContextBarProps {
  /** 選択中の都道府県名 */
  prefecture: string;
  /** 都道府県フィルタのみ解除した戻り先（他フィルタは保持） */
  backHref: string;
}

/**
 * 都道府県で絞り込み中に、全国マップの代わりに表示する文脈バー。
 * 地理的コンテキストの提示と、全国マップへの復帰導線を兼ねる。
 */
export function PrefectureContextBar({ prefecture, backHref }: PrefectureContextBarProps) {
  return (
    <div className="flex items-center justify-between gap-4 bg-white rounded-lg shadow-sm p-4 border border-gray-100">
      <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">
        {prefecture}の保護動物
      </h2>
      <Link
        href={backHref}
        className="inline-flex items-center gap-1 text-sm text-[var(--color-primary-700)] hover:underline focus:outline-none focus:ring-2 focus:ring-[var(--color-focus-ring)] focus:ring-offset-2 rounded"
      >
        <span aria-hidden="true">←</span> 全国マップに戻る
      </Link>
    </div>
  );
}
