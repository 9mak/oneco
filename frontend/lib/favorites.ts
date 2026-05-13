'use client';

/**
 * お気に入り管理（LocalStorage ベース、認証不要）
 *
 * 動物 ID の配列を localStorage に保存。複数タブで同期するため
 * storage イベントを購読する hook を提供する。
 */

import { useCallback, useSyncExternalStore } from 'react';

const STORAGE_KEY = 'oneco:favorites';
const STORAGE_EVENT = 'oneco-favorites-changed';

function parseRaw(raw: string | null): number[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((v): v is number => typeof v === 'number');
  } catch {
    return [];
  }
}

function readFromStorage(): number[] {
  if (typeof window === 'undefined') return [];
  return parseRaw(window.localStorage.getItem(STORAGE_KEY));
}

function writeToStorage(ids: number[]): void {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(ids));
  // 同一タブ内の他コンポーネントに通知（storage イベントは別タブにしか飛ばないため）
  window.dispatchEvent(new CustomEvent(STORAGE_EVENT));
}

// useSyncExternalStore の getSnapshot は同じ参照を返さないと無限ループになるため、
// raw 文字列をキーにスナップショットをキャッシュする。
let cachedRaw: string | null | undefined = undefined;
let cachedSnapshot: number[] = [];

function getSnapshot(): number[] {
  if (typeof window === 'undefined') return cachedSnapshot;
  let raw: string | null;
  try {
    raw = window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return cachedSnapshot;
  }
  if (raw === cachedRaw) return cachedSnapshot;
  cachedRaw = raw;
  cachedSnapshot = parseRaw(raw);
  return cachedSnapshot;
}

const EMPTY_SNAPSHOT: number[] = [];
function getServerSnapshot(): number[] {
  return EMPTY_SNAPSHOT;
}

function subscribe(callback: () => void): () => void {
  if (typeof window === 'undefined') return () => {};
  window.addEventListener('storage', callback);
  window.addEventListener(STORAGE_EVENT, callback);
  return () => {
    window.removeEventListener('storage', callback);
    window.removeEventListener(STORAGE_EVENT, callback);
  };
}

/**
 * お気に入り全件 + 操作関数を返す
 */
export function useFavorites() {
  const favorites = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

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
