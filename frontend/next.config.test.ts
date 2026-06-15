import { describe, it, expect } from 'vitest';
import nextConfig from './next.config';

/**
 * 2026-06-15 本番で GA4/GTM が CSP にブロックされ計測が完全停止していた。
 * CSP に Google Analytics 系ホストが含まれることを保証するリグレッションテスト。
 */
async function getCsp(): Promise<string> {
  if (typeof nextConfig.headers !== 'function') {
    throw new Error('next.config.headers() が未定義');
  }
  const headers = await nextConfig.headers();
  const csp = headers
    .flatMap((h) => h.headers)
    .find((h) => h.key === 'Content-Security-Policy');
  if (!csp) throw new Error('Content-Security-Policy ヘッダが見つからない');
  return csp.value;
}

function directive(csp: string, name: string): string {
  const found = csp
    .split(';')
    .map((d) => d.trim())
    .find((d) => d.startsWith(`${name} `));
  if (!found) throw new Error(`${name} ディレクティブが見つからない: ${csp}`);
  return found;
}

describe('next.config CSP', () => {
  it('script-src で googletagmanager.com を許可する (gtag 読込)', async () => {
    const scriptSrc = directive(await getCsp(), 'script-src');
    expect(scriptSrc).toContain('https://www.googletagmanager.com');
  });

  it('connect-src で google-analytics.com とリージョン別サブドメインを許可する (計測ビーコン)', async () => {
    const connectSrc = directive(await getCsp(), 'connect-src');
    expect(connectSrc).toContain('https://www.google-analytics.com');
    expect(connectSrc).toContain('https://*.google-analytics.com');
  });

  it("self を維持する (既存の正当な読込を壊さない)", async () => {
    const csp = await getCsp();
    expect(directive(csp, 'script-src')).toContain("'self'");
    expect(directive(csp, 'connect-src')).toContain("'self'");
    expect(directive(csp, 'default-src')).toContain("'self'");
  });
});
