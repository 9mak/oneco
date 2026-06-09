/**
 * サイトの公開ベース URL を返す。sitemap / robots / canonical / OGP がこの値を使う。
 *
 * 本番(Vercel production)で NEXT_PUBLIC_SITE_URL が未設定 / localhost のままだと、
 * sitemap・canonical・OGP の全 URL が localhost を指し、Google が 1 件もインデックス
 * できず検索流入がゼロになる(= 集客が止まり使命が機能不全に陥る最悪の設定漏れ)。
 * これを silent に通さないため、Vercel の本番デプロイでだけ build を明示的に失敗させる。
 *
 * CI / ローカルの `next build` / preview デプロイ(VERCEL_ENV !== 'production')では、
 * localhost フォールバックを許容してビルドを壊さない。
 */
export function getSiteUrl(): string {
  const raw = process.env.NEXT_PUBLIC_SITE_URL;
  const isVercelProduction = process.env.VERCEL_ENV === 'production';

  if (isVercelProduction) {
    const missing = !raw;
    const isLocalhost = !!raw && (raw.includes('localhost') || raw.includes('127.0.0.1'));
    if (missing || isLocalhost) {
      throw new Error(
        'NEXT_PUBLIC_SITE_URL が本番(Vercel production)で未設定または localhost のままです。' +
          'Vercel の Production 環境変数に実ドメイン(https://...)を設定してください。' +
          'このまま公開すると sitemap / canonical / OGP が localhost を指し、' +
          '検索エンジンに 1 件もインデックスされません。',
      );
    }
    return raw;
  }

  return raw || 'http://localhost:3000';
}
