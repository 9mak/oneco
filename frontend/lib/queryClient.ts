/**
 * TanStack Query デフォルト設定
 * Stale-While-Revalidate戦略、クライアントサイドキャッシング、エラーリトライ設定
 */

import { QueryClient } from '@tanstack/react-query';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      /**
       * staleTime: 5分間はstaleとして扱わない
       * 動物データは頻繁に更新されないため、5分間はキャッシュデータを使用
       */
      staleTime: 5 * 60 * 1000, // 5分

      /**
       * gcTime (旧cacheTime): 10分間メモリキャッシュ保持
       * ガベージコレクション前にキャッシュを保持する時間
       */
      gcTime: 10 * 60 * 1000, // 10分

      /**
       * retry: エラー時3回リトライ
       */
      retry: 3,

      /**
       * retryDelay: exponential backoff (1秒 → 2秒 → 4秒)
       * 最大30秒まで
       */
      retryDelay: (attemptIndex) =>
        Math.min(1000 * 2 ** attemptIndex, 30000),

      /**
       * refetchOnWindowFocus: ウィンドウフォーカス時に再フェッチ
       * ユーザーがタブを切り替えた時に最新データを取得
       */
      refetchOnWindowFocus: true,

      /**
       * refetchOnReconnect: ネットワーク再接続時に再フェッチ
       */
      refetchOnReconnect: true,
    },
  },
});
