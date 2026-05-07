'use client';

/**
 * お気に入り管理（LocalStorage ベース、認証不要）
 *
 * 動物 ID の配列を localStorage に保存。複数タブで同期するため
 * storage イベントを購読する hook を提供する。
 */

import { useCallback, useEffect, useState } from 'react';

const STORAGE_KEY = 'oneco:favorites';
const STORAGE_EVENT = 'oneco-favorites-changed';

function readFromStorage(): number[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((v): v is number => typeof v === 'number');
  } catch {
    return [];
  }
}

function writeToStorage(ids: number[]): void {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(ids));
  // 同一タブ内の他コンポーネントに通知（storage イベントは別タブにしか飛ばないため）
  window.dispatchEvent(new CustomEvent(STORAGE_EVENT));
}

/**
 * お気に入り全件 + 操作関数を返す
 */
export function useFavorites() {
  const [favorites, setFavorites] = useState<number[]>([]);

  useEffect(() => {
    setFavorites(readFromStorage());

    const sync = () => setFavorites(readFromStorage());
    window.addEventListener('storage', sync);
    window.addEventListener(STORAGE_EVENT, sync);
    return () => {
      window.removeEventListener('storage', sync);
      window.removeEventListener(STORAGE_EVENT, sync);
    };
  }, []);

  const add = useCallback((id: number) => {
    const current = readFromStorage();
    if (!current.includes(id)) {
      writeToStorage([...current, id]);
    }
  }, []);

  const remove = useCallback((id: number) => {
    const current = readFromStorage();
    writeToStorage(current.filter((v) => v !== id));
  }, []);

  const toggle = useCallback((id: number) => {
    const current = readFromStorage();
    if (current.includes(id)) {
      writeToStorage(current.filter((v) => v !== id));
    } else {
      writeToStorage([...current, id]);
    }
  }, []);

  const has = useCallback((id: number) => favorites.includes(id), [favorites]);

  return { favorites, add, remove, toggle, has };
}
