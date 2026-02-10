/**
 * ContactInfo Component
 * 自治体連絡先（収容場所、電話番号）とカテゴリ別案内文を表示
 * Requirements: 4.1, 4.2, 4.3, 4.4
 */

'use client';

interface ContactInfoProps {
  /** 収容場所 */
  location: string;
  /** 電話番号 */
  phone: string | null;
  /** カテゴリ ("adoption": 譲渡対象, "lost": 迷子) */
  category: 'adoption' | 'lost';
}

export function ContactInfo({ location, phone, category }: ContactInfoProps) {
  // カテゴリ別案内文
  const categoryMessage = {
    adoption: '譲渡についてはお電話でお問い合わせください',
    lost: '飼い主の方はお早めにご連絡ください',
  };

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-6 shadow-sm">
      <h2 className="text-xl font-semibold text-gray-900 mb-4">
        お問い合わせ先
      </h2>

      {/* 収容場所 */}
      <div className="mb-4">
        <dt className="text-sm font-medium text-gray-500 mb-1">収容場所</dt>
        <dd className="text-base text-gray-900">{location}</dd>
      </div>

      {/* 電話番号 */}
      {phone && (
        <div className="mb-4">
          <dt className="text-sm font-medium text-gray-500 mb-1">電話番号</dt>
          <dd>
            <a
              href={`tel:${phone}`}
              className="text-base text-[var(--color-primary-500)] hover:text-[var(--color-primary-700)] underline focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[var(--color-primary-500)] rounded"
            >
              {phone}
            </a>
          </dd>
        </div>
      )}

      {/* カテゴリ別案内文 */}
      <div
        className="mt-6 p-4 bg-blue-50 border-l-4 border-[var(--color-primary-500)] rounded"
        role="alert"
      >
        <p className="text-sm text-gray-700">
          {categoryMessage[category]}
        </p>
      </div>
    </div>
  );
}
