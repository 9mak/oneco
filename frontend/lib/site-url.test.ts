import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { getSiteUrl } from './site-url';

const originalEnv = { ...process.env };

describe('getSiteUrl', () => {
  beforeEach(() => {
    process.env = { ...originalEnv };
    delete process.env.NEXT_PUBLIC_SITE_URL;
    delete process.env.VERCEL_ENV;
  });

  afterEach(() => {
    process.env = { ...originalEnv };
  });

  it('有効な本番URLが設定されていればそれを返す', () => {
    process.env.NEXT_PUBLIC_SITE_URL = 'https://oneco.example';
    expect(getSiteUrl()).toBe('https://oneco.example');
  });

  it('未設定の開発/CI環境では localhost にフォールバックする', () => {
    expect(getSiteUrl()).toBe('http://localhost:3000');
  });

  it('Vercel 本番デプロイで未設定なら build を失敗させる', () => {
    process.env.VERCEL_ENV = 'production';
    expect(() => getSiteUrl()).toThrow(/NEXT_PUBLIC_SITE_URL/);
  });

  it('Vercel 本番デプロイで localhost のままなら build を失敗させる', () => {
    process.env.VERCEL_ENV = 'production';
    process.env.NEXT_PUBLIC_SITE_URL = 'http://localhost:3000';
    expect(() => getSiteUrl()).toThrow();
  });

  it('Vercel 本番デプロイで 127.0.0.1 でも build を失敗させる', () => {
    process.env.VERCEL_ENV = 'production';
    process.env.NEXT_PUBLIC_SITE_URL = 'http://127.0.0.1:3000';
    expect(() => getSiteUrl()).toThrow();
  });

  it('Vercel 本番デプロイで有効な https URL なら通す', () => {
    process.env.VERCEL_ENV = 'production';
    process.env.NEXT_PUBLIC_SITE_URL = 'https://oneco.example';
    expect(getSiteUrl()).toBe('https://oneco.example');
  });

  it('Vercel preview デプロイでは localhost を許容する(本番のみ厳格)', () => {
    process.env.VERCEL_ENV = 'preview';
    expect(getSiteUrl()).toBe('http://localhost:3000');
  });
});
