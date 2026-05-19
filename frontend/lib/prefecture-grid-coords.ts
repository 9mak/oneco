/**
 * 47 都道府県の SVG 配置座標（簡略化日本列島レイアウト）
 *
 * 真の地理座標ではなく、列島の形状を「四角タイル」で再現したシンボル地図。
 * - 外部依存ゼロ（d3-geo / TopoJSON 不要）
 * - サイズ: 14 列 × 16 行のグリッド
 * - 1 セル = 56px (svg unit)
 *
 * 北海道 (上) から沖縄 (左下) へ。各タイルのサイズは均一にして
 * 視覚的に揃える。a11y 上は数字 + ラベル + 色で識別する。
 */
export interface PrefectureCoord {
  /** 0-indexed grid 列 (左→右) */
  col: number;
  /** 0-indexed grid 行 (上→下) */
  row: number;
}

export const PREFECTURE_COORDS: Record<string, PrefectureCoord> = {
  北海道: { col: 11, row: 0 },
  青森県: { col: 11, row: 2 },
  秋田県: { col: 10, row: 3 },
  岩手県: { col: 12, row: 3 },
  山形県: { col: 10, row: 4 },
  宮城県: { col: 12, row: 4 },
  新潟県: { col: 10, row: 5 },
  福島県: { col: 12, row: 5 },
  富山県: { col: 9, row: 6 },
  群馬県: { col: 11, row: 6 },
  栃木県: { col: 12, row: 6 },
  茨城県: { col: 13, row: 6 },
  石川県: { col: 8, row: 6 },
  福井県: { col: 8, row: 7 },
  長野県: { col: 9, row: 7 },
  埼玉県: { col: 11, row: 7 },
  東京都: { col: 12, row: 7 },
  千葉県: { col: 13, row: 7 },
  京都府: { col: 7, row: 8 },
  滋賀県: { col: 8, row: 8 },
  岐阜県: { col: 9, row: 8 },
  山梨県: { col: 10, row: 8 },
  神奈川県: { col: 11, row: 8 },
  静岡県: { col: 10, row: 9 },
  愛知県: { col: 9, row: 9 },
  三重県: { col: 8, row: 9 },
  奈良県: { col: 7, row: 9 },
  大阪府: { col: 6, row: 9 },
  兵庫県: { col: 5, row: 9 },
  鳥取県: { col: 4, row: 8 },
  島根県: { col: 3, row: 8 },
  岡山県: { col: 5, row: 10 },
  広島県: { col: 4, row: 10 },
  山口県: { col: 3, row: 10 },
  和歌山県: { col: 6, row: 10 },
  徳島県: { col: 5, row: 11 },
  香川県: { col: 4, row: 11 },
  愛媛県: { col: 3, row: 11 },
  高知県: { col: 4, row: 12 },
  福岡県: { col: 2, row: 11 },
  大分県: { col: 3, row: 12 },
  佐賀県: { col: 1, row: 11 },
  長崎県: { col: 0, row: 11 },
  熊本県: { col: 1, row: 12 },
  宮崎県: { col: 2, row: 13 },
  鹿児島県: { col: 1, row: 13 },
  沖縄県: { col: 0, row: 15 },
};

/** SVG 全体の列数 / 行数 / セル 1 辺の px サイズ */
export const GRID_COLS = 14;
export const GRID_ROWS = 16;
export const CELL_SIZE = 56;
