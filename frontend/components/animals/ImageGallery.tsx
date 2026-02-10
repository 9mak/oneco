/**
 * ImageGallery Component
 * 画像ギャラリー表示、画像クリックで拡大モーダル表示
 * キーボードナビゲーション（矢印キー）でギャラリー内移動
 * Requirements: 2.4, 2.5, 6.1, 6.2
 */

'use client';

import { useState } from 'react';
import Image from 'next/image';
import { ImageModal } from './ImageModal';

interface ImageGalleryProps {
  /** 画像URL配列 */
  imageUrls: string[];
  /** 画像の代替テキスト（動物の種別など） */
  alt: string;
}

export function ImageGallery({ imageUrls, alt }: ImageGalleryProps) {
  const [selectedImageIndex, setSelectedImageIndex] = useState<number | null>(null);

  // 画像配列が空の場合
  if (!imageUrls || imageUrls.length === 0) {
    return (
      <div className="bg-gray-100 rounded-lg p-8 text-center">
        <p className="text-gray-500">画像がありません</p>
      </div>
    );
  }

  // 画像クリックハンドラー
  const handleImageClick = (index: number) => {
    setSelectedImageIndex(index);
  };

  // モーダルを閉じる
  const handleCloseModal = () => {
    setSelectedImageIndex(null);
  };

  // 次の画像へ移動
  const handleNextImage = () => {
    if (selectedImageIndex !== null && selectedImageIndex < imageUrls.length - 1) {
      setSelectedImageIndex(selectedImageIndex + 1);
    }
  };

  // 前の画像へ移動
  const handlePrevImage = () => {
    if (selectedImageIndex !== null && selectedImageIndex > 0) {
      setSelectedImageIndex(selectedImageIndex - 1);
    }
  };

  return (
    <div>
      {/* ギャラリーグリッド */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        {imageUrls.map((imageUrl, index) => (
          <button
            key={index}
            onClick={() => handleImageClick(index)}
            className="relative aspect-square overflow-hidden rounded-lg bg-gray-100 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[var(--color-primary-500)] transition-transform hover:scale-105"
            aria-label={`${alt}の画像${index + 1}を拡大表示`}
          >
            <Image
              src={imageUrl}
              alt={`${alt}の画像${index + 1}`}
              fill
              sizes="(max-width: 768px) 50vw, 33vw"
              className="object-cover"
              loading="lazy"
            />
          </button>
        ))}
      </div>

      {/* 画像拡大モーダル */}
      {selectedImageIndex !== null && (
        <ImageModal
          imageUrl={imageUrls[selectedImageIndex]}
          alt={`${alt}の画像${selectedImageIndex + 1}`}
          onClose={handleCloseModal}
        />
      )}
    </div>
  );
}
