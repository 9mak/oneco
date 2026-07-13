/**
 * バックエンド API のベース URL を返す。動物データの取得 (animals / archive /
 * sitemap / OGP 画像) がこの値を使う。
 *
 * Vercel 上 (production / preview) で未設定のまま `|| 'http://localhost:8000'` に
 * silent fallback すると、ビルド時 ECONNREFUSED や空データページが「原因不明の
 * 不具合」として現れる (2026-07-12 の PR preview 障害)。これを silent に通さない
 * ため、Vercel デプロイでは未設定 / localhost を明示エラーにする。
 *
 * ローカル開発・CI の `next build` (VERCEL_ENV なし) では localhost:8000 に
 * フォールバックしてビルドを壊さない。優先順位は lib/admin.ts と同じ
 * BACKEND_INTERNAL_URL (server-only) → NEXT_PUBLIC_API_BASE_URL。
 */
export function getApiBaseUrl(): string {
  const raw = process.env.BACKEND_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL;
  const onVercel = !!process.env.VERCEL_ENV;

  if (onVercel) {
    const missing = !raw;
    const isLocalhost = !!raw && (raw.includes('localhost') || raw.includes('127.0.0.1'));
    if (missing || isLocalhost) {
      throw new Error(
        'BACKEND_INTERNAL_URL / NEXT_PUBLIC_API_BASE_URL が Vercel デプロイで未設定' +
          'または localhost のままです。Vercel の環境変数 (Production と Preview の両方) に ' +
          'バックエンド API の実 URL (https://...) を設定してください。' +
          'このままでは全ページの動物データ取得が失敗します。',
      );
    }
    return raw as string;
  }

  return raw || 'http://localhost:8000';
}
