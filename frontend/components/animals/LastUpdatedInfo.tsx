/**
 * LastUpdatedInfo Component
 * oneco側の収集(クロール)が最後に成功した日時を淡々と表示する。
 *
 * Why: サイトの収集が壊れて何日も更新が止まっていても、DBの古いデータが
 * そのまま「最新情報」の顔で表示され続ける問題があった。ただし検知ロジックの
 * 誤検知や「自治体側にはまだ掲載されているがoneco側のツールが壊れているだけ」
 * の可能性もあるため、「壊れています」等の断定はせず、客観的な日付情報だけを
 * 示してユーザー自身の判断(元サイト確認)を促す。
 */

'use client';

interface LastUpdatedInfoProps {
  /** oneco側の収集が最後に成功した日時 (ISO 8601形式)。null/undefinedなら非表示 */
  lastCollectedAt?: string | null;
}

function formatDate(value: string): string | null {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  const year = parsed.getFullYear();
  const month = String(parsed.getMonth() + 1).padStart(2, '0');
  const day = String(parsed.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function LastUpdatedInfo({ lastCollectedAt }: LastUpdatedInfoProps) {
  if (!lastCollectedAt) {
    return null;
  }
  const formatted = formatDate(lastCollectedAt);
  if (!formatted) {
    return null;
  }

  return (
    <span className="text-xs text-gray-500" title="oneco がこの情報を最後に確認した日付">
      最終更新: {formatted}
    </span>
  );
}
