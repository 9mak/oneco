/**
 * ヒートマップの quantile bin 計算ユーティリティ
 *
 * 都道府県別の件数を一様分布で N 段階に分割する。0 件は bin 0、それ以外は 1..N に振り分ける。
 */

/**
 * 0 を除いた値の集合を昇順にソートし、N 段階に分割するときの上限値 (N-1 個) を返す。
 */
export function computeQuantileBins(counts: number[], n: number): number[] {
  const nonZero = counts.filter((c) => c > 0).sort((a, b) => a - b);
  if (nonZero.length === 0) return [];
  const bins: number[] = [];
  for (let i = 1; i < n; i++) {
    const idx = Math.min(
      Math.floor((nonZero.length * i) / n),
      nonZero.length - 1,
    );
    bins.push(nonZero[idx]);
  }
  return bins;
}

/**
 * 1 件の count が何 bin に属するかを返す。0 = データなし、1..N = ヒートマップ濃度。
 */
export function getBinIndex(count: number, bins: number[]): number {
  if (count === 0) return 0;
  for (let i = 0; i < bins.length; i++) {
    if (count <= bins[i]) return i + 1;
  }
  return bins.length + 1;
}
