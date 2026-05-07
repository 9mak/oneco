# 画像永続化・重複検出 ロードマップ

**作成日:** 2026-05-07
**状態:** Phase 1 完了、Phase 2-3 未着手

---

## 背景

現状の課題：
- **画像が外部依存**: `animals.image_urls` は元サイトの URL を保持。元サイトが画像を消すとリンク切れ
- **重複動物の混在**: 県動愛 + 政令指定都市など、同じ動物が複数サイトで掲載されると oneco 上でも別レコードとして二重表示
- **インフラ未活用**: `image_hashes` テーブルと `ImageStorageService` クラスは既存だが、メイン収集フローに組み込まれていない

## 既存の資産

| ファイル | 内容 |
|---|---|
| `src/data_collector/infrastructure/database/models.py:ImageHash` | hash/local_path/file_size を保持するテーブル定義 |
| `src/data_collector/infrastructure/image_storage.py:LocalImageStorage` | ハッシュベースのディレクトリ階層で画像を保存 |
| `src/data_collector/infrastructure/image_storage_service.py:ImageStorageService` | URL からダウンロード + SHA-256 ハッシュ + 重複検出 |
| `src/data_collector/infrastructure/database/image_hash_repository.py` | image_hashes テーブルへの CRUD |
| `animals.local_image_paths` カラム | スキーマ済み、現在常に空配列 |

## ロードマップ

### Phase 1（MVP）✅ 完了

- [x] `image_hashes` テーブルに URL ベースの SHA-256 を蓄積（重複検出の最低限）
- [x] `URLHashRecorder` ヘルパー実装 (`src/data_collector/infrastructure/url_hash_recorder.py`)
- [x] `CollectorService._save_via_db_connection` にフック追加（保存成功時に画像URLを記録）
- [x] 失敗時のフォールバック（メイン保存処理は中断しない）
- [x] テスト: ヘルパー単体 10件 + 統合テスト 2件
- [ ] **未対応**: `_save_via_repository` 経路（テスト用途のためスキップ。Phase 2 で必要なら統一検討）
- [ ] **未対応**: 同一 URL を持つ動物の発見 API（蓄積データの活用は Phase 3 で）

### Phase 2（次フェーズ）— 画像永続化 + Supabase Storage 連携

**目的**: 元サイト消失でも画像が見える状態を保つ。

**設計：**
1. **Supabase Storage バケット** 作成（公開読み取り）
   - バケット名: `animal-images`
   - パス構造: `{hash[:2]}/{hash[2:4]}/{hash}.{ext}` （LocalImageStorage と同形式）
2. **新規アダプタ** `SupabaseImageStorage`（`LocalImageStorage` のインタフェース互換）
   - service_role_key で upload
   - public read URL を返却
3. **収集パイプラインに組み込み**
   - LlmAdapter または CollectorService で各 animal の image_urls をダウンロード
   - SHA-256 ハッシュ計算 → image_hashes テーブル参照
   - 既存ハッシュ → local_path 再利用
   - 新規ハッシュ → Supabase Storage アップロード + image_hashes 追加
   - `animals.local_image_paths` を更新
4. **フロント対応**
   - `AnimalCard` / `ImageGallery`: `local_image_paths.length > 0 ? local_image_paths : image_urls`
   - 元サイト消失でも画像表示が維持される

**必要な env:**
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY` (CI と Cloud Run の Secret Manager に設定)

**容量試算:**
- 67 動物 × 5 画像 × 平均 200KB ≒ 67MB（現状）
- 5,000 動物（全国想定）× 5 画像 × 200KB ≒ 5GB
- Supabase Storage 無料枠: 1GB → Pro プラン（月$25）で 100GB
- もしくは GCS で従量課金（5GB なら月数十円）

### Phase 3 — 知覚ハッシュ（Perceptual Hash）による真の重複検出

**目的**: 同じ動物が複数サイトで違う URL の同じ画像で掲載されているケースの検出。

**設計：**
1. **Perceptual hash ライブラリ** 導入: `imagehash` (Python)
2. アルゴリズム: pHash（DCT ベース、リサイズ・圧縮に頑健）
3. ハッシュ距離（Hamming distance）が閾値以下 → 同一画像判定
4. **重複動物グルーピング**:
   - 同一画像を持つ動物 IDs を `canonical_animal_id` でリンク
   - 検索時はデフォルトで canonical のみ表示
5. **Backend API**:
   - `GET /animals?dedupe=true`（デフォルト ON）
   - `GET /animals/{id}/duplicates` → 同じ画像の他レコード一覧
6. **Frontend**:
   - 詳細ページで「他自治体でも掲載されています: [link]」表示
   - 一覧では canonical のみ表示でクリーンに

**スキーマ変更:**
```sql
ALTER TABLE animals ADD COLUMN canonical_animal_id INTEGER REFERENCES animals(id);
ALTER TABLE image_hashes ADD COLUMN phash VARCHAR(16);  -- 64bit phash
CREATE INDEX idx_image_hashes_phash ON image_hashes(phash);
```

### Phase 4 — 画像最適化

- WebP 変換（古いブラウザ向けに JPEG fallback）
- リサイズ（200x200 サムネ + 800x600 詳細）
- CDN（Cloudflare R2 + Cloudflare Images）

---

## 工数見積もり

| Phase | 内容 | 工数 |
|---|---|---|
| 1 | URL ハッシュ重複検出 MVP | 半日 |
| 2 | Supabase Storage 永続化 | 1〜2 日 |
| 3 | Perceptual hash 重複検出 | 2〜3 日 |
| 4 | 画像最適化 / CDN | 1 日 |

合計 4〜6 日程度。Phase 2 までで実用上の課題は概ね解決。

---

## 今回（Phase 1 MVP）の方針

実装範囲を絞り、スキーマ拡張も避ける：
- 既存の `image_hashes` テーブルに URL の SHA-256 を蓄積するヘルパーを用意
- コレクター内では呼び出さない（Phase 2 で wire up）
- ドキュメントとして本ファイルを残す

これにより、Phase 2 着手時の足場が整う。
