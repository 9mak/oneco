import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { getApiBaseUrl } from './api-base-url';

const originalEnv = { ...process.env };

describe('getApiBaseUrl', () => {
  beforeEach(() => {
    process.env = { ...originalEnv };
    delete process.env.BACKEND_INTERNAL_URL;
    delete process.env.NEXT_PUBLIC_API_BASE_URL;
    delete process.env.VERCEL_ENV;
  });

  afterEach(() => {
    process.env = { ...originalEnv };
  });

  it('BACKEND_INTERNAL_URL を最優先で返す', () => {
    process.env.BACKEND_INTERNAL_URL = 'https://internal.example';
    process.env.NEXT_PUBLIC_API_BASE_URL = 'https://public.example';
    expect(getApiBaseUrl()).toBe('https://internal.example');
  });

  it('BACKEND_INTERNAL_URL がなければ NEXT_PUBLIC_API_BASE_URL を返す', () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = 'https://public.example';
    expect(getApiBaseUrl()).toBe('https://public.example');
  });

  it('未設定の開発/CI環境では localhost:8000 にフォールバックする', () => {
    expect(getApiBaseUrl()).toBe('http://localhost:8000');
  });

  it('Vercel production で未設定ならビルドを失敗させる', () => {
    process.env.VERCEL_ENV = 'production';
    expect(() => getApiBaseUrl()).toThrow(/NEXT_PUBLIC_API_BASE_URL/);
  });

  it('Vercel preview で未設定ならビルドを失敗させる（localhost に silent fallback しない）', () => {
    process.env.VERCEL_ENV = 'preview';
    expect(() => getApiBaseUrl()).toThrow(/NEXT_PUBLIC_API_BASE_URL/);
  });

  it('Vercel 上で localhost のままならビルドを失敗させる', () => {
    process.env.VERCEL_ENV = 'preview';
    process.env.NEXT_PUBLIC_API_BASE_URL = 'http://localhost:8000';
    expect(() => getApiBaseUrl()).toThrow();
  });

  it('Vercel 上で 127.0.0.1 でもビルドを失敗させる', () => {
    process.env.VERCEL_ENV = 'production';
    process.env.NEXT_PUBLIC_API_BASE_URL = 'http://127.0.0.1:8000';
    expect(() => getApiBaseUrl()).toThrow();
  });

  it('Vercel 上で正しい URL が設定されていればそれを返す', () => {
    process.env.VERCEL_ENV = 'preview';
    process.env.NEXT_PUBLIC_API_BASE_URL = 'https://oneco-api.example';
    expect(getApiBaseUrl()).toBe('https://oneco-api.example');
  });
});
