import { PREFECTURE_COORDS } from './prefecture-grid-coords';

/**
 * 47 都道府県名のリスト。
 *
 * 地図座標の単一ソース（PREFECTURE_COORDS）からキーを導出し、重複定義を避ける。
 * 並びは北海道→沖縄の地理順（PREFECTURE_COORDS の定義順）。
 */
export const PREFECTURES: readonly string[] = Object.keys(PREFECTURE_COORDS);

/** 文字列が 47 都道府県のいずれかの正式名称か判定する。 */
export function isValidPrefecture(name: string): boolean {
  return Object.prototype.hasOwnProperty.call(PREFECTURE_COORDS, name);
}
