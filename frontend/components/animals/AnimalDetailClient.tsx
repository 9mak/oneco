/**
 * AnimalDetailClient Component
 * 動物詳細表示クライアントコンポーネント
 * カテゴリ、動物情報、画像ギャラリー、連絡先情報を表示
 * Requirements: 2.2, 2.3, 2.7, 4.1-4.5, 6.4
 */

'use client';

import { useRouter } from 'next/navigation';
import { AnimalPublic } from '@/types/animal';
import { CategoryBadge } from '@/components/ui/CategoryBadge';
import { ImageGallery } from './ImageGallery';
import { ContactInfo } from './ContactInfo';
import { ExternalLink } from './ExternalLink';

interface AnimalDetailClientProps {
  /** 動物データ */
  animal: AnimalPublic;
}

export function AnimalDetailClient({ animal }: AnimalDetailClientProps) {
  const router = useRouter();

  // 「一覧に戻る」ボタンハンドラー
  const handleBackToList = () => {
    router.push('/');
  };

  // 年齢表示（月単位を年月に変換）
  const formatAge = (months: number | null): string => {
    if (months === null) return '不明';
    if (months < 12) return `約${months}ヶ月`;
    const years = Math.floor(months / 12);
    const remainingMonths = months % 12;
    if (remainingMonths === 0) return `約${years}歳`;
    return `約${years}歳${remainingMonths}ヶ月`;
  };

  // 収容日フォーマット
  const formatDate = (dateString: string): string => {
    const date = new Date(dateString);
    return date.toLocaleDateString('ja-JP', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
  };

  return (
    <div className="max-w-5xl mx-auto">
      {/* 戻るボタン */}
      <button
        onClick={handleBackToList}
        className="inline-flex items-center text-[var(--color-primary-500)] hover:text-[var(--color-primary-700)] mb-6 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[var(--color-primary-500)] rounded p-2 -ml-2"
        aria-label="一覧に戻る"
      >
        <svg
          className="w-5 h-5 mr-2"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          xmlns="http://www.w3.org/2000/svg"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M15 19l-7-7 7-7"
          />
        </svg>
        一覧に戻る
      </button>

      {/* カテゴリバッジ（目立つ位置） */}
      <div className="mb-4">
        <CategoryBadge category={animal.category} size="lg" />
      </div>

      {/* 動物情報ヘッダー */}
      <header className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">
          {animal.species}
        </h1>
        <p className="text-lg text-gray-600">
          {animal.location}で保護
        </p>
      </header>

      {/* メインコンテンツ */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* 左カラム: 画像ギャラリー */}
        <div className="lg:col-span-2">
          <section>
            <h2 className="text-xl font-semibold text-gray-900 mb-4">
              写真
            </h2>
            <ImageGallery imageUrls={animal.image_urls} alt={animal.species} />
          </section>
        </div>

        {/* 右カラム: 詳細情報と連絡先 */}
        <div className="space-y-6">
          {/* 詳細情報 */}
          <section className="bg-white border border-gray-200 rounded-lg p-6 shadow-sm">
            <h2 className="text-xl font-semibold text-gray-900 mb-4">
              詳細情報
            </h2>

            <dl className="space-y-3">
              <div>
                <dt className="text-sm font-medium text-gray-500">種別</dt>
                <dd className="text-base text-gray-900">{animal.species}</dd>
              </div>

              <div>
                <dt className="text-sm font-medium text-gray-500">性別</dt>
                <dd className="text-base text-gray-900">{animal.sex}</dd>
              </div>

              <div>
                <dt className="text-sm font-medium text-gray-500">推定年齢</dt>
                <dd className="text-base text-gray-900">{formatAge(animal.age_months)}</dd>
              </div>

              {animal.color && (
                <div>
                  <dt className="text-sm font-medium text-gray-500">毛色</dt>
                  <dd className="text-base text-gray-900">{animal.color}</dd>
                </div>
              )}

              {animal.size && (
                <div>
                  <dt className="text-sm font-medium text-gray-500">体格</dt>
                  <dd className="text-base text-gray-900">{animal.size}</dd>
                </div>
              )}

              <div>
                <dt className="text-sm font-medium text-gray-500">収容日</dt>
                <dd className="text-base text-gray-900">{formatDate(animal.shelter_date)}</dd>
              </div>
            </dl>
          </section>

          {/* 連絡先情報 */}
          <ContactInfo
            location={animal.location}
            phone={animal.phone}
            category={animal.category}
          />

          {/* 元のページを見るボタン */}
          <ExternalLink sourceUrl={animal.source_url} />
        </div>
      </div>
    </div>
  );
}
