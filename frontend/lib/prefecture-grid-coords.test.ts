import { describe, expect, it } from 'vitest';

import {
  CELL_SIZE,
  GRID_COLS,
  GRID_ROWS,
  PREFECTURE_COORDS,
} from './prefecture-grid-coords';

describe('PREFECTURE_COORDS', () => {
  it('47 都道府県を全て含む', () => {
    expect(Object.keys(PREFECTURE_COORDS)).toHaveLength(47);
  });

  it('全ての座標がグリッド範囲内', () => {
    for (const [pref, { col, row }] of Object.entries(PREFECTURE_COORDS)) {
      expect(col, `${pref} col`).toBeGreaterThanOrEqual(0);
      expect(col, `${pref} col`).toBeLessThan(GRID_COLS);
      expect(row, `${pref} row`).toBeGreaterThanOrEqual(0);
      expect(row, `${pref} row`).toBeLessThan(GRID_ROWS);
    }
  });

  it('同一座標に 2 県以上が配置されない（オーバーラップなし）', () => {
    const seen = new Set<string>();
    const collisions: string[] = [];
    for (const [pref, { col, row }] of Object.entries(PREFECTURE_COORDS)) {
      const key = `${col},${row}`;
      if (seen.has(key)) collisions.push(`${pref} at ${key}`);
      seen.add(key);
    }
    expect(collisions).toEqual([]);
  });

  it('CELL_SIZE が描画 SVG に妥当な値', () => {
    expect(CELL_SIZE).toBeGreaterThan(0);
    expect(GRID_COLS * CELL_SIZE).toBeGreaterThan(0);
    expect(GRID_ROWS * CELL_SIZE).toBeGreaterThan(0);
  });
});
