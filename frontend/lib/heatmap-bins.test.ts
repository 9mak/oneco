import { describe, expect, it } from 'vitest';

import { computeQuantileBins, getBinIndex } from './heatmap-bins';

describe('computeQuantileBins', () => {
  it('全要素が 0 の場合は空配列を返す', () => {
    expect(computeQuantileBins([0, 0, 0], 5)).toEqual([]);
  });

  it('空配列でも空配列を返す', () => {
    expect(computeQuantileBins([], 5)).toEqual([]);
  });

  it('5 段階で 4 個の境界値を返す', () => {
    const counts = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
    const bins = computeQuantileBins(counts, 5);
    expect(bins).toHaveLength(4);
  });

  it('0 を含む配列でも 0 をスキップして bin を計算する', () => {
    const counts = [0, 0, 10, 20, 30, 40, 50];
    const bins = computeQuantileBins(counts, 5);
    expect(bins).toHaveLength(4);
    expect(bins[0]).toBeGreaterThan(0);
  });

  it('単一要素では全 bin が同じ値', () => {
    expect(computeQuantileBins([42], 5)).toEqual([42, 42, 42, 42]);
  });
});

describe('getBinIndex', () => {
  it('count=0 は bin 0', () => {
    expect(getBinIndex(0, [10, 20, 30, 40])).toBe(0);
  });

  it('count=1 は最小 bin (1)', () => {
    expect(getBinIndex(1, [10, 20, 30, 40])).toBe(1);
  });

  it('最大 bin 上限値ぴったりはその bin', () => {
    expect(getBinIndex(20, [10, 20, 30, 40])).toBe(2);
  });

  it('全 bin 上限を超える値は最大 bin', () => {
    expect(getBinIndex(100, [10, 20, 30, 40])).toBe(5);
  });

  it('空 bins (データが極端に薄い) のときは 1 以上を 1 として扱う', () => {
    expect(getBinIndex(5, [])).toBe(1);
    expect(getBinIndex(0, [])).toBe(0);
  });
});
