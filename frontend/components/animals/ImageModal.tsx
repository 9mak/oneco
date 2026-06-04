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
  /** 原寸大を確認するための出典元URL (任意。指定時は「元のページで見る」リンクを表示) */
  sourceUrl?: string;
}

export function ImageModal({ imageUrl, alt, onClose, sourceUrl }: ImageModalProps) {
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

        {/* 画像 - 著作権配慮 (47条の7「軽微利用」の趣旨) でモーダルも縮小サムネイル化。
            原寸大は元サイトで確認する導線を下部に提供する。priority は外す (LCP対象外)。 */}
        <div className="relative w-full h-full">
          <Image
            src={imgSrc}
            alt={alt}
            width={640}
            height={480}
            className="object-contain max-h-[70vh] w-auto h-auto"
            unoptimized={imgSrc === PLACEHOLDER_IMAGE ? true : undefined}
            onError={() => setImgSrc(PLACEHOLDER_IMAGE)}
          />
        </div>

        {sourceUrl && (
          <p className="mt-3 text-center text-sm text-white/80">
            <a
              href={sourceUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="underline hover:text-white focus:outline-none focus:ring-2 focus:ring-white rounded"
            >
              原寸大の画像は元のページでご確認ください ↗
            </a>
          </p>
        )}
      </div>
    </div>,
    document.body
  );
}
