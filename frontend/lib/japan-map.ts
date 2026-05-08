import { geoMercator, geoPath } from 'd3-geo';
import { feature } from 'topojson-client';
import type { FeatureCollection, Geometry } from 'geojson';
import type { Topology } from 'topojson-specification';

export interface PrefectureFeatureProperties {
  nam_ja: string;
  nam: string;
  id: number;
}

export interface PrefectureGeometry {
  prefecture: string;
  d: string;
  centroid: [number, number];
}

const VIEW_WIDTH = 600;
const VIEW_HEIGHT = 600;

export function projectPrefectures(topology: Topology): {
  width: number;
  height: number;
  geometries: PrefectureGeometry[];
} {
  const geo = feature(
    topology,
    topology.objects.japan,
  ) as FeatureCollection<Geometry, PrefectureFeatureProperties>;

  const projection = geoMercator().fitSize([VIEW_WIDTH, VIEW_HEIGHT], geo);
  const path = geoPath(projection);

  const geometries: PrefectureGeometry[] = geo.features
    .map((f) => {
      const d = path(f);
      const centroid = path.centroid(f);
      if (!d) return null;
      return {
        prefecture: f.properties.nam_ja,
        d,
        centroid: [centroid[0], centroid[1]] as [number, number],
      };
    })
    .filter((g): g is PrefectureGeometry => g !== null);

  return { width: VIEW_WIDTH, height: VIEW_HEIGHT, geometries };
}

/**
 * 件数 → 色クラス（オレンジ系ヒートマップ）
 *
 * 0件はグレー、最大値の何分位に入るかで5段階。
 */
export function bucketColor(count: number, max: number): string {
  if (count === 0) return '#f3f4f6';
  if (max === 0) return '#f3f4f6';
  const ratio = count / max;
  if (ratio < 0.2) return '#fed7aa';
  if (ratio < 0.4) return '#fdba74';
  if (ratio < 0.6) return '#fb923c';
  if (ratio < 0.8) return '#f97316';
  return '#ea580c';
}
