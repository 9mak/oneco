import { describe, it, expect } from 'vitest';
import { PREFECTURES, isValidPrefecture } from './prefectures';

describe('prefectures', () => {
  it('47 都道府県を持つ', () => {
    expect(PREFECTURES).toHaveLength(47);
  });

  it('主要な都道府県を含む（北から南まで）', () => {
    for (const p of ['北海道', '東京都', '大阪府', '高知県', '沖縄県']) {
      expect(PREFECTURES).toContain(p);
    }
  });

  it('isValidPrefecture が正しく判定する', () => {
    expect(isValidPrefecture('東京都')).toBe(true);
    expect(isValidPrefecture('高知県')).toBe(true);
    expect(isValidPrefecture('東京')).toBe(false); // 「都」が無い
    expect(isValidPrefecture('foo')).toBe(false);
    expect(isValidPrefecture('')).toBe(false);
  });
});
