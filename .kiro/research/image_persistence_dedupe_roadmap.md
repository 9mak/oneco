# 画像永続化・重複検出 ロードマップ

**作成日:** 2026-05-07
**状態:** Phase 1 完了、Phase 2 完了（方針変更あり）、Phase 3-4 未着手
**最終更新:** 2026-05-07

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

### Phase 2 ✅ 完了（方針変更）— onError プレースホルダーフォールバック

**当初案**: 全画像を Supabase Storage に永続化 → リンク切れ防止
**採用案**: フロントの onError でプレースホルダーへフォールバック → ストレージコストゼロ

**方針変更の理由（2026-05-07）：**
- 永続化はストレージコストが**累積で線形増加**（1年20GB増、5年100GB超）
- アクティブ動物の元サイトURLは大半は生きており、表示には十分
- 「次のクロール実行までに元サイトが画像を消した」窓だけがリンク切れリスク
  → その窓は**プレースホルダー表示で十分**（数時間〜数日の一時的なUX劣化）
- アーカイブされた動物は status を見て出し分け or プレースホルダーで足りる

**実装内容：**
- `frontend/lib/images.ts`: `PLACEHOLDER_IMAGE` 定数を集約
- `ImageGallery.tsx`: 各サムネイルの onError → 個別差替（他画像はそのまま）。失敗画像はモーダル拡大時もプレースホルダー
- `ImageModal.tsx`: imgSrc を state 化し onError でフォールバック、imageUrl 切替時はリセット
- `AnimalCard.tsx`: 既存のプレースホルダー参照を新定数に統一（既に onError 実装済みだったため挙動は不変）
- テスト 3件追加（全 78 件 Green）

**結果：**
- 元サイトが画像を削除してもリンク切れが見えなくなる
- 追加コスト: $0（Supabase Storage バケット不要、新規 env 不要）
- スキーマ変更: なし（`animals.local_image_paths` は未使用のまま）

**捨てた設計（参考）：**
当初は `SupabaseImageStorage` アダプタ → 収集パイプライン組み込み → `local_image_paths` 更新 → フロントで優先表示、という流れを想定していた。
コスト懸念とアーカイブ動物のUXトレードオフを精査し、永続化なしで成立すると判断。
画像本体のハッシュベース重複検出が必要になったら Phase 3（pHash）で別途検討する。

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
| 1 | URL ハッシュ重複検出 MVP | 半日（完了） |
| 2 | onError プレースホルダーフォールバック | 半日（完了 / 方針変更） |
| 3 | Perceptual hash 重複検出 | 2〜3 日 |
| 4 | 画像最適化 / CDN | 1 日（永続化前提なら不要） |

合計 1日（Phase 1+2 完了済み）+ Phase 3 を残す。
画像永続化を見送ったので Phase 4（CDN）はスコープから外す可能性あり。

---

## 今回（Phase 1 MVP）の方針

実装範囲を絞り、スキーマ拡張も避ける：
- 既存の `image_hashes` テーブルに URL の SHA-256 を蓄積するヘルパーを用意
- コレクター内では呼び出さない（Phase 2 で wire up）
- ドキュメントとして本ファイルを残す

これにより、Phase 2 着手時の足場が整う。

## Phase 2 での方針変更の振り返り（2026-05-07）

Phase 2 着手時にコスト試算を精査した結果、画像永続化は割に合わないと判断：

- 永続化のコストは **「累積動物数 × 平均画像枚数 × 平均サイズ」** で線形増加
- 5年で100GB超 → Supabase Pro の100GB枠を超えて従量課金へ
- 一方、リンク切れリスクは「次のクロール実行までの数時間〜数日」のみ
- そのウィンドウは **プレースホルダー表示で十分許容できる UX 劣化**
- アーカイブ動物は譲渡完了の記録としては価値があるが、画像が無くても文脈は伝わる

→ Phase 2 は「永続化」ではなく **「onError フォールバック」** で完了。
Phase 1 で蓄積を始めた `image_hashes` の URL ハッシュは、Phase 3（pHash）の文脈で用途を再定義する想定。
