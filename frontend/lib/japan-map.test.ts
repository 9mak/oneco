import { describe, it, expect } from 'vitest';
import { bucketColor, projectPrefectures } from './japan-map';
import type { Topology } from 'topojson-specification';

const FAKE_TOPO: Topology = {
  type: 'Topology',
  arcs: [
    [
      [0, 0],
      [1, 0],
      [1, 1],
      [0, 1],
      [0, 0],
    ],
    [
      [2, 0],
      [3, 0],
      [3, 1],
      [2, 1],
      [2, 0],
    ],
  ],
  objects: {
    japan: {
      type: 'GeometryCollection',
      geometries: [
        {
          type: 'Polygon',
          arcs: [[0]],
          properties: { nam: 'TestA', nam_ja: 'テスト県A', id: 1 },
        },
        {
          type: 'Polygon',
          arcs: [[1]],
          properties: { nam: 'TestB', nam_ja: 'テスト県B', id: 2 },
        },
      ],
    },
  },
};

describe('projectPrefectures', () => {
  it('returns SVG path data and centroid for each prefecture', () => {
    const result = projectPrefectures(FAKE_TOPO);
    expect(result.geometries).toHaveLength(2);
    const a = result.geometries.find((g) => g.prefecture === 'テスト県A');
    expect(a).toBeDefined();
    expect(a?.d).toMatch(/^[ML]/);
    expect(typeof a?.centroid[0]).toBe('number');
    expect(typeof a?.centroid[1]).toBe('number');
  });

  it('produces fixed viewBox dimensions', () => {
    const result = projectPrefectures(FAKE_TOPO);
    expect(result.width).toBe(600);
    expect(result.height).toBe(600);
  });
});

describe('bucketColor', () => {
  it('returns gray for count=0', () => {
    expect(bucketColor(0, 100)).toBe('#f3f4f6');
  });

  it('returns gray when max=0 (no data)', () => {
    expect(bucketColor(0, 0)).toBe('#f3f4f6');
    expect(bucketColor(5, 0)).toBe('#f3f4f6');
  });

  it('returns progressively darker oranges as ratio increases', () => {
    const max = 100;
    const colors = [
      bucketColor(10, max), // 10% < 20%
      bucketColor(30, max), // 30% < 40%
      bucketColor(50, max), // 50% < 60%
      bucketColor(70, max), // 70% < 80%
      bucketColor(100, max), // 100%
    ];
    expect(new Set(colors).size).toBe(5);
    expect(colors[4]).toBe('#ea580c');
  });
});
