/**
 * TypeScript type definitions corresponding to backend API schemas
 * Based on Pydantic AnimalPublic schema
 */

/**
 * 保護動物の公開情報
 */
export interface AnimalPublic {
  /** 動物ID */
  id: number;
  /** 種別 (例: "犬", "猫") */
  species: string;
  /** 性別 (例: "男の子", "女の子", "不明") */
  sex: string;
  /** 推定年齢（月単位） */
  age_months: number | null;
  /** 毛色 */
  color: string | null;
  /** 体格 */
  size: string | null;
  /** 収容日 (ISO 8601形式) */
  shelter_date: string;
  /** 収容場所 */
  location: string;
  /** 都道府県名 (例: '高知県') */
  prefecture: string | null;
  /** 電話番号 */
  phone: string | null;
  /** 画像URL配列 */
  image_urls: string[];
  /** 元のページURL */
  source_url: string;
  /** カテゴリ ("adoption": 譲渡対象, "lost": 迷子, "sheltered": 収容中) */
  category: 'adoption' | 'lost' | 'sheltered';
}

/**
 * ページネーションメタデータ
 */
export interface PaginationMeta {
  /** 総件数 */
  total_count: number;
  /** 1ページあたりの件数 */
  limit: number;
  /** オフセット */
  offset: number;
  /** 現在のページ番号 */
  current_page: number;
  /** 総ページ数 */
  total_pages: number;
  /** 次のページが存在するか */
  has_next: boolean;
}

/**
 * ページネーション付きレスポンス (ジェネリック型)
 */
export interface PaginatedResponse<T> {
  /** データアイテム配列 */
  items: T[];
  /** ページネーションメタデータ */
  meta: PaginationMeta;
}

/**
 * 動物の現在状態 (status)
 *
 * category（情報の種類）と直交する軸。
 * デフォルトは 'sheltered'（収容中）— 譲渡済 / 返還済 / 死亡した動物は明示指定で表示。
 */
export type AnimalStatus = 'sheltered' | 'adopted' | 'returned' | 'deceased';

/**
 * フィルタ状態
 */
export interface FilterState {
  /** カテゴリ（情報の種類: 譲渡対象 / 迷子 / 収容情報） */
  category?: 'adoption' | 'lost' | 'sheltered';
  /** ステータス（動物の現在状態。未指定時は 'sheltered' を暗黙適用） */
  status?: AnimalStatus;
  /** 種別フィルタ */
  species?: '犬' | '猫';
  /** 性別フィルタ */
  sex?: '男の子' | '女の子' | '不明';
  /** 地域フィルタ (部分一致検索) */
  location?: string;
  /** 都道府県フィルタ (完全一致) */
  prefecture?: string;
}
