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
import { PLACEHOLDER_IMAGE } from '@/lib/images';

interface ImageGalleryProps {
  /** 画像URL配列 */
  imageUrls: string[];
  /** 画像の代替テキスト（動物の種別など） */
  alt: string;
}

export function ImageGallery({ imageUrls, alt }: ImageGalleryProps) {
  const [selectedImageIndex, setSelectedImageIndex] = useState<number | null>(null);
  const [erroredIndices, setErroredIndices] = useState<Set<number>>(new Set());

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

  const resolveSrc = (index: number, url: string) =>
    erroredIndices.has(index) ? PLACEHOLDER_IMAGE : url;

  const handleImageError = (index: number) => {
    setErroredIndices((prev) => {
      if (prev.has(index)) return prev;
      const next = new Set(prev);
      next.add(index);
      return next;
    });
  };

  return (
    <div>
      {/* ギャラリーグリッド */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        {imageUrls.map((imageUrl, index) => {
          const src = resolveSrc(index, imageUrl);
          const isPlaceholder = src === PLACEHOLDER_IMAGE;
          return (
            <button
              key={index}
              onClick={() => handleImageClick(index)}
              className="relative aspect-square overflow-hidden rounded-lg bg-gray-100 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[var(--color-primary-500)] transition-transform hover:scale-105"
              aria-label={`${alt}の画像${index + 1}を拡大表示`}
            >
              <Image
                src={src}
                alt={`${alt}の画像${index + 1}`}
                fill
                sizes="(max-width: 768px) 50vw, 33vw"
                className="object-cover"
                loading="lazy"
                unoptimized={isPlaceholder ? true : undefined}
                onError={() => handleImageError(index)}
              />
            </button>
          );
        })}
      </div>

      {/* 画像拡大モーダル */}
      {selectedImageIndex !== null && (
        <ImageModal
          imageUrl={resolveSrc(selectedImageIndex, imageUrls[selectedImageIndex])}
          alt={`${alt}の画像${selectedImageIndex + 1}`}
          onClose={handleCloseModal}
        />
      )}
    </div>
  );
}
