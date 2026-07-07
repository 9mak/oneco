import { describe, it, expect } from 'vitest';
import imageLoader from './image-loader';

describe('imageLoader (wsrv.nl)', () => {
  it('リモート URL は wsrv.nl 経由の縮小 WebP URL に変換する', () => {
    const url = imageLoader({
      src: 'https://www.city.matsuyama.ehime.jp/aigo/neko.jpg',
      width: 384,
      quality: 60,
    });
    const parsed = new URL(url);
    expect(parsed.origin).toBe('https://wsrv.nl');
    expect(parsed.searchParams.get('url')).toBe(
      'https://www.city.matsuyama.ehime.jp/aigo/neko.jpg'
    );
    expect(parsed.searchParams.get('w')).toBe('384');
    expect(parsed.searchParams.get('q')).toBe('60');
    expect(parsed.searchParams.get('output')).toBe('webp');
    expect(parsed.searchParams.get('we')).toBe('1');
  });

  it('quality 未指定時は著作権配慮の既定値 60 を使う', () => {
    const url = imageLoader({ src: 'https://example.jp/dog.jpg', width: 640 });
    expect(new URL(url).searchParams.get('q')).toBe('60');
  });

  it('ローカル静的アセットは変換せずそのまま返す', () => {
    expect(imageLoader({ src: '/images/about/pom-1.jpg', width: 1200 })).toBe(
      '/images/about/pom-1.jpg'
    );
    expect(imageLoader({ src: '/placeholder-animal.svg', width: 640 })).toBe(
      '/placeholder-animal.svg'
    );
  });

  it('幅ごとに異なる URL を返す (srcset が機能する)', () => {
    const a = imageLoader({ src: 'https://example.jp/cat.jpg', width: 256 });
    const b = imageLoader({ src: 'https://example.jp/cat.jpg', width: 640 });
    expect(a).not.toBe(b);
  });
});
