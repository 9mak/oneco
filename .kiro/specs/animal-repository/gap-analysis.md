# ギャップ分析レポート: animal-repository

## 1. 分析サマリー

### スコープ
animal-repository は既存の animal-api-persistence（AnimalData、AnimalRepository、Animal ORMモデル）を拡張し、以下の高度機能を追加する：
- ステータス管理（sheltered/adopted/returned/deceased）
- データ保持ポリシー（譲渡後6ヶ月アーカイブ）
- 画像永続化（ローカルストレージ）
- 運用監視機能

### 主な課題
1. **ステータス管理**: 現行 Animal モデルに status, status_changed_at, outcome_date, status_history フィールドが存在しない
2. **アーカイブ機能**: アーカイブテーブル・処理が未実装、バックグラウンドジョブ基盤がない
3. **画像永続化**: 画像ダウンロード・ローカルストレージ機能が完全に欠落
4. **後方互換性**: 既存 API との互換性維持が必要

### 推奨アプローチ
**ハイブリッドアプローチ**を推奨：既存 Animal モデル・AnimalRepository を拡張しつつ、画像ストレージサービス・アーカイブサービスは新規コンポーネントとして作成。

---

## 2. 現行資産マッピング

### 2.1 既存コンポーネント

| 既存資産 | パス | 役割 |
|---------|------|------|
| AnimalData (Pydantic) | `src/data_collector/domain/models.py` | ドメインモデル（species, sex, age_months, image_urls, source_url, category 等） |
| Animal (SQLAlchemy ORM) | `src/data_collector/infrastructure/database/models.py` | DBモデル（id, species, sex, shelter_date, image_urls, source_url, category 等） |
| AnimalRepository | `src/data_collector/infrastructure/database/repository.py` | CRUD操作（save_animal, get_animal_by_id, list_animals） |
| API Routes | `src/data_collector/infrastructure/api/routes.py` | REST API（GET /animals, GET /animals/{id}） |
| AnimalPublic (Schema) | `src/data_collector/infrastructure/api/schemas.py` | API レスポンススキーマ |
| Alembic Migrations | `alembic/versions/*.py` | スキーマバージョン管理 |
| notification-manager | `src/notification_manager/` | 通知サービス（参考パターン: MetricsCollector, AlertManager, AuditLogger） |

### 2.2 アーキテクチャパターン

| パターン | 既存実装例 | 備考 |
|---------|-----------|------|
| Repository パターン | `AnimalRepository`, `NotificationRepository` | AsyncSession ベース |
| Pydantic/ORM 変換 | `_to_orm()`, `_to_pydantic()` | 双方向変換メソッド |
| フィルタリング・ページネーション | `list_animals(species, category, limit, offset)` | 既存パターン踏襲 |
| Alembic マイグレーション | `33c0ccd7c108`, `6134989ff064` | 増分マイグレーション |
| メトリクス/監視 | `MetricsCollector`, `AlertManager` | notification-manager 実装参照 |
| バリデーション | `@field_validator` | Pydantic v2 スタイル |

---

## 3. 要件別ギャップ分析

### Requirement 1: ステータス管理

| 受入条件 | 既存資産 | ギャップ |
|---------|---------|---------|
| 1.1 status フィールド（4値） | なし | **Missing** - Animal モデルに status カラム追加必要 |
| 1.2 デフォルト 'sheltered' | なし | **Missing** - save_animal() でデフォルト設定 |
| 1.3 status_changed_at 記録 | なし | **Missing** - DateTime カラム追加必要 |
| 1.4 status_history 保持 | なし | **Missing** - JSONB or 別テーブル検討必要 |
| 1.5 outcome_date 記録 | なし | **Missing** - Date カラム追加必要 |
| 1.6 ステータスフィルタリング | category フィルタ実装あり | **Extension** - list_animals に status パラメータ追加 |

**複雑度**: 中程度（DB スキーマ変更、ビジネスロジック追加）

### Requirement 2: データ保持ポリシー

| 受入条件 | 既存資産 | ギャップ |
|---------|---------|---------|
| 2.1 6ヶ月アクティブ保持 | なし | **Missing** - 期間計算ロジック必要 |
| 2.2 アーカイブテーブル移動 | なし | **Missing** - animals_archive テーブル・移動処理必要 |
| 2.3 アーカイブ読み取り専用 | なし | **Missing** - ArchiveRepository 作成必要 |
| 2.4 保持期間設定可能 | なし | **Missing** - 環境変数/設定ファイル |
| 2.5 アーカイブ中の一貫性 | なし | **Missing** - トランザクション設計必要 |
| 2.6 処理ログ記録 | AuditLogger パターンあり | **Extension** - 参照パターンあり |
| 2.7 エラー時通知 | NotificationClient あり | **Extension** - 既存通知基盤活用 |

**複雑度**: 高（バックグラウンドジョブ、トランザクション管理）
**Research Needed**: スケジューラー選定（APScheduler, Celery, システム cron）

### Requirement 3: 画像永続化

| 受入条件 | 既存資産 | ギャップ |
|---------|---------|---------|
| 3.1 画像ダウンロード | なし | **Missing** - HTTP クライアント + ダウンローダー必要 |
| 3.2 UUID ファイル命名 | なし | **Missing** - 命名ロジック必要 |
| 3.3 local_image_paths 記録 | image_urls のみ | **Missing** - 新カラム追加必要 |
| 3.4 ダウンロード中の fallback | なし | **Missing** - 非同期処理設計必要 |
| 3.5 失敗時ログ・継続 | ロギング基盤あり | **Extension** - エラーハンドリング |
| 3.6 ハッシュ重複検出 | なし | **Missing** - SHA-256 ハッシュ計算必要 |
| 3.7 アーカイブ時画像移動 | なし | **Missing** - Req 2 と連携必要 |
| 3.8 画像形式検証 | なし | **Missing** - MIME タイプ検証必要 |

**複雑度**: 高（ファイルシステム操作、非同期処理、重複検出）
**Research Needed**: ストレージ設計（ローカル vs S3 互換）、画像処理ライブラリ選定

### Requirement 4: データ整合性

| 受入条件 | 既存資産 | ギャップ |
|---------|---------|---------|
| 4.1 source_url ユニーク制約 | 実装済み | **None** - 既存制約維持 |
| 4.2 ステータス遷移検証 | なし | **Missing** - 状態遷移バリデーション必要 |
| 4.3 ValidationError 発生 | Pydantic validator パターンあり | **Extension** - 新バリデータ追加 |
| 4.4 トランザクション原子性 | session.commit() パターンあり | **Extension** - ステータス履歴も含める |
| 4.5 ロールバック・エラー通知 | 基本パターンあり | **Extension** - 既存パターン拡張 |

**複雑度**: 低〜中程度（ビジネスルール実装）

### Requirement 5: 後方互換性

| 受入条件 | 既存資産 | ギャップ |
|---------|---------|---------|
| 5.1 AnimalData 互換性 | AnimalData モデル | **Constraint** - 新フィールドは Optional 必須 |
| 5.2 既存 API 動作維持 | list_animals, get_animal_by_id | **Constraint** - デフォルト動作変更禁止 |
| 5.3 ステータスフィルタなし時全返却 | なし | **Extension** - アーカイブ除外ロジック |
| 5.4 category との共存 | category 実装済み | **None** - 既存フィールド維持 |
| 5.5 Alembic 非破壊マイグレーション | Alembic 基盤あり | **Constraint** - ALTER TABLE のみ |

**複雑度**: 低（設計制約の遵守）

### Requirement 6: 運用・監視

| 受入条件 | 既存資産 | ギャップ |
|---------|---------|---------|
| 6.1 ステータス別集計メトリクス | MetricsCollector (notification-manager) | **Extension** - パターン流用 |
| 6.2 画像ストレージ監視・アラート | AlertManager (notification-manager) | **Extension** - 閾値設定追加 |
| 6.3 アーカイブ対象日次レポート | なし | **Missing** - レポート生成ジョブ必要 |
| 6.4 画像DL失敗率アラート | AlertManager パターンあり | **Extension** - 新アラートタイプ |
| 6.5 監査ログ | AuditLogger (notification-manager) | **Extension** - 状態変更ログ追加 |

**複雑度**: 中程度（notification-manager パターン流用可能）

---

## 4. 実装アプローチ評価

### Option A: 既存コンポーネント拡張

**対象**:
- Animal ORM モデルにカラム追加（status, status_changed_at, outcome_date, local_image_paths）
- AnimalData に Optional フィールド追加
- AnimalRepository に新メソッド追加

**メリット**:
- ✅ 既存パターンとの一貫性維持
- ✅ ファイル数最小化
- ✅ 学習コスト低

**デメリット**:
- ❌ AnimalRepository が肥大化
- ❌ 画像・アーカイブ処理が複雑化

**適用範囲**: Req 1（ステータス管理）, Req 4（データ整合性）, Req 5（後方互換性）

### Option B: 新規コンポーネント作成

**対象**:
- ImageStorageService（画像ダウンロード、ハッシュ管理、ストレージ操作）
- ArchiveService（アーカイブ判定、移動処理）
- ArchiveRepository（アーカイブデータアクセス）
- StatusHistory テーブル

**メリット**:
- ✅ 責務分離が明確
- ✅ 単体テスト容易
- ✅ 将来の拡張性

**デメリット**:
- ❌ ファイル数増加
- ❌ 統合テストの複雑化

**適用範囲**: Req 2（アーカイブ）, Req 3（画像永続化）

### Option C: ハイブリッドアプローチ（推奨）

**戦略**:
1. **Phase 1**: Animal モデル・AnimalRepository 拡張（Req 1, 4, 5）
2. **Phase 2**: ImageStorageService 新規作成（Req 3）
3. **Phase 3**: ArchiveService 新規作成（Req 2）
4. **Phase 4**: 監視機能拡張（Req 6）

**メリット**:
- ✅ 段階的リスク軽減
- ✅ 既存コードへの影響最小化
- ✅ 各フェーズで動作確認可能

**デメリット**:
- ❌ 計画の複雑化

---

## 5. 工数・リスク評価

### 工数見積もり

| 領域 | 工数 | 根拠 |
|------|------|------|
| Req 1: ステータス管理 | M | DB変更 + ビジネスロジック追加 |
| Req 2: アーカイブ | L | 新テーブル + バックグラウンドジョブ + トランザクション設計 |
| Req 3: 画像永続化 | L | 外部依存（HTTP）+ ファイルI/O + 重複検出アルゴリズム |
| Req 4: データ整合性 | S | 既存パターン拡張 |
| Req 5: 後方互換性 | S | 設計制約のみ |
| Req 6: 監視 | M | notification-manager パターン流用 |

**総合工数**: L（1-2週間）

### リスク評価

| リスク | レベル | 軽減策 |
|--------|-------|-------|
| アーカイブ処理中のデータ整合性 | 高 | 詳細なトランザクション設計、ロック戦略検討 |
| 画像ダウンロード失敗率 | 中 | リトライ戦略、フォールバック設計 |
| バックグラウンドジョブ管理 | 中 | スケジューラー選定調査必要 |
| 後方互換性の破壊 | 中 | 既存テストの完全実行、API契約テスト |

---

## 6. Research Needed（設計フェーズで調査）

1. **スケジューラー選定**: APScheduler vs Celery vs システム cron
   - アーカイブジョブ、日次レポート生成に必要

2. **画像ストレージ設計**:
   - ローカルファイルシステム vs S3互換オブジェクトストレージ
   - ディレクトリ構造（日付ベース vs ハッシュベース）

3. **ステータス履歴保存方式**:
   - JSONB カラム（シンプル）vs 別テーブル（クエリ効率）

4. **アーカイブ戦略**:
   - 物理移動（別テーブル）vs 論理削除（archived_at カラム）

---

## 7. 設計フェーズへの推奨事項

1. **優先順位**: Req 1 → Req 4 → Req 5 → Req 3 → Req 2 → Req 6
   - ステータス管理を基盤として、依存機能を順次追加

2. **段階的マイグレーション**:
   - 既存データに `status = 'sheltered'` のデフォルト値を設定
   - `local_image_paths` は空配列で初期化

3. **テスト戦略**:
   - 既存テスト全実行を必須とする
   - 後方互換性テストを追加

4. **監視先行**:
   - メトリクス/アラート基盤を早期に構築し、画像DL・アーカイブ処理の監視に活用

---

## 8. 次のステップ

ギャップ分析が完了しました。次は設計フェーズに進みます：

```bash
/kiro:spec-design animal-repository
```

または要件に修正が必要な場合：

```bash
/kiro:spec-requirements animal-repository
```
