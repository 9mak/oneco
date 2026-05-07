/**
 * ImageModal Component
 * 画像拡大表示モーダル - Escキーで閉じる、背景クリックで閉じる
 * React Portalでbody直下にマウント、ARIA属性でアクセシビリティ確保
 * Requirements: 2.5, 6.2
 */

'use client';

import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import Image from 'next/image';
import { PLACEHOLDER_IMAGE } from '@/lib/images';

interface ImageModalProps {
  /** 表示する画像URL */
  imageUrl: string;
  /** 画像の代替テキスト */
  alt: string;
  /** モーダルを閉じるコールバック */
  onClose: () => void;
}

export function ImageModal({ imageUrl, alt, onClose }: ImageModalProps) {
  const [imgSrc, setImgSrc] = useState(imageUrl);

  // imageUrl が切り替わったら src をリセット
  useEffect(() => {
    setImgSrc(imageUrl);
  }, [imageUrl]);

  // Escキーで閉じる
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    document.addEventListener('keydown', handleEscape);
    // モーダル表示中はbodyのスクロールを無効化
    document.body.style.overflow = 'hidden';

    return () => {
      document.removeEventListener('keydown', handleEscape);
      document.body.style.overflow = 'unset';
    };
  }, [onClose]);

  // React Portalでbody直下にマウント
  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-90 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="画像拡大表示"
      onClick={onClose}
    >
      {/* モーダルコンテンツ */}
      <div
        className="relative max-w-7xl max-h-full"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 閉じるボタン */}
        <button
          onClick={onClose}
          className="absolute -top-12 right-0 text-white hover:text-gray-300 focus:outline-none focus:ring-2 focus:ring-white rounded p-2 min-h-[44px] min-w-[44px]"
          aria-label="モーダルを閉じる"
        >
          <svg
            className="w-8 h-8"
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
              d="M6 18L18 6M6 6l12 12"
            />
          </svg>
        </button>

        {/* 画像 */}
        <div className="relative w-full h-full">
          <Image
            src={imgSrc}
            alt={alt}
            width={1200}
            height={800}
            className="object-contain max-h-[80vh] w-auto h-auto"
            priority
            unoptimized={imgSrc === PLACEHOLDER_IMAGE ? true : undefined}
            onError={() => setImgSrc(PLACEHOLDER_IMAGE)}
          />
        </div>
      </div>
    </div>,
    document.body
  );
}
