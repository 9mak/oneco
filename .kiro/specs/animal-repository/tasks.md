# Implementation Plan: animal-repository

## Overview

animal-repository の実装タスクを4つのフェーズに分けて進行する。各フェーズは設計書の Migration Strategy に対応している。

- **Phase 1**: スキーマ拡張とドメインモデル
- **Phase 2**: ステータス管理機能
- **Phase 3**: 画像永続化機能
- **Phase 4**: アーカイブ・監視機能

---

## Tasks

### Phase 1: スキーマ拡張とドメインモデル

- [x] 1. データベーススキーマ拡張
- [x] 1.1 (P) animals テーブルに新規カラムを追加する Alembic マイグレーションを作成
  - status カラム（VARCHAR(20)、デフォルト 'sheltered'）を追加
  - status_changed_at カラム（TIMESTAMP WITH TIME ZONE）を追加
  - outcome_date カラム（DATE）を追加
  - local_image_paths カラム（JSONB、デフォルト '[]'）を追加
  - 既存データに影響を与えない ALTER TABLE 形式で実装
  - 各カラムに適切なインデックスを追加（status, outcome_date, status_changed_at）
  - _Requirements: 1.1, 1.3, 1.5, 3.3, 5.5_

- [x] 1.2 (P) animal_status_history テーブルを作成する Alembic マイグレーションを作成
  - id, animal_id, old_status, new_status, changed_at, changed_by カラムを定義
  - animals テーブルへの外部キー制約（ON DELETE CASCADE）を設定
  - ステータス値のチェック制約を追加
  - animal_id と changed_at にインデックスを追加
  - _Requirements: 1.4_

- [x] 1.3 (P) image_hashes テーブルを作成する Alembic マイグレーションを作成
  - id, hash, local_path, file_size, created_at カラムを定義
  - hash カラムにユニーク制約とインデックスを追加
  - _Requirements: 3.6_

- [x] 1.4 (P) animals_archive テーブルを作成する Alembic マイグレーションを作成
  - animals テーブルと同一スキーマ + original_id, archived_at カラムを定義
  - source_url にユニーク制約を追加
  - species, archived_at, original_id にインデックスを追加
  - _Requirements: 2.2, 2.3_

- [x] 2. ドメインモデル拡張
- [x] 2.1 AnimalStatus 列挙型と AnimalData モデルの拡張
  - sheltered, adopted, returned, deceased の4値を持つ列挙型を定義
  - AnimalData に status, status_changed_at, outcome_date, local_image_paths フィールドを追加
  - 新規フィールドは全て Optional として後方互換性を確保
  - 既存のバリデーション（species, sex, category）を維持
  - _Requirements: 1.1, 1.3, 1.5, 3.3, 5.1_

- [x] 2.2 Animal ORM モデルの拡張
  - 新規カラム（status, status_changed_at, outcome_date, local_image_paths）を定義
  - デフォルト値を設定（status='sheltered', local_image_paths=[]）
  - _to_orm() と _to_pydantic() メソッドを更新して新フィールドを含める
  - _Requirements: 1.1, 1.2, 1.3, 1.5, 3.3_

- [x] 2.3 StatusTransitionValidator を実装
  - 有効なステータス遷移の定義（VALID_TRANSITIONS セット）
  - validate_transition() メソッドで遷移検証
  - StatusTransitionError 例外クラスの定義
  - deceased からの遷移を禁止するルール
  - _Requirements: 4.2, 4.3_

- [x] 2.4 StatusHistoryEntry データクラスと StatusHistory ORM モデルを定義
  - animal_id, old_status, new_status, changed_at, changed_by フィールド
  - AnimalStatus 列挙型との連携
  - _Requirements: 1.4_

### Phase 2: ステータス管理機能

- [x] 3. リポジトリ層のステータス管理機能
- [x] 3.1 StatusHistoryRepository を実装
  - record_transition() でステータス遷移を記録
  - get_history() で動物のステータス履歴を取得
  - AsyncSession を使用した非同期 DB 操作
  - _Requirements: 1.4_

- [x] 3.2 AnimalRepository にステータス更新機能を追加
  - update_status() メソッドを実装（トランザクション内で履歴も記録）
  - StatusTransitionValidator による遷移検証を統合
  - outcome_date の自動設定（adopted/returned の場合）
  - ロールバック対応のエラーハンドリング
  - _Requirements: 1.1, 1.3, 1.5, 4.2, 4.3, 4.4, 4.5_

- [x] 3.3 AnimalRepository にステータスフィルタリング機能を追加
  - list_animals() に status パラメータを追加
  - list_animals_by_status() メソッドを実装
  - ステータス未指定時は全ステータス（アーカイブ除く）を返却
  - 既存の API 動作を維持
  - _Requirements: 1.6, 5.2, 5.3_

- [x] 4. ステータス管理 API エンドポイント
- [x] 4.1 ステータス更新 API を実装
  - PATCH /animals/{id}/status エンドポイントを追加
  - StatusUpdateRequest/Response スキーマを定義
  - StatusTransitionError を 422 Unprocessable Entity にマッピング
  - 成功時は更新後の動物データを返却
  - _Requirements: 1.1, 1.3, 1.5, 4.2, 4.3_

- [x] 4.2 既存 API のステータスフィルタリング対応
  - GET /animals に status クエリパラメータを追加
  - AnimalPublic スキーマに status 関連フィールドを追加（オプション）
  - 既存クライアントへの後方互換性を維持
  - _Requirements: 1.6, 5.2, 5.3, 5.4_

- [x] 5. ステータス管理のテスト
- [x] 5.1 StatusTransitionValidator のユニットテスト
  - 全有効遷移パターンの検証
  - 無効遷移（deceased からの遷移など）の拒否確認
  - StatusTransitionError の発生確認
  - _Requirements: 4.2, 4.3_

- [x] 5.2 AnimalRepository.update_status() の統合テスト
  - ステータス更新と履歴記録の原子性検証
  - トランザクションロールバックの確認
  - outcome_date 自動設定の検証
  - _Requirements: 1.3, 1.4, 1.5, 4.4, 4.5_

- [x] 5.3 ステータス管理 API の E2E テスト
  - 正常系：ステータス更新成功
  - 異常系：不正遷移で 422 エラー
  - フィルタリング：ステータスによる検索
  - _Requirements: 1.1, 1.6, 4.2, 4.3_

### Phase 3: 画像永続化機能

- [x] 6. 画像ストレージ基盤
- [x] 6.1 (P) LocalImageStorage を実装
  - ハッシュベースのディレクトリ構造（{hash[:2]}/{hash[2:4]}/{hash}.{ext}）
  - save() で画像を保存しパスを返却
  - move() でアーカイブストレージへ移動
  - delete() で画像を削除
  - exists() でハッシュの存在チェック
  - get_usage_bytes() でストレージ使用量を取得
  - _Requirements: 3.1, 3.2, 3.7_

- [x] 6.2 (P) ImageHash ORM モデルと重複検出機能を実装
  - hash, local_path, file_size, created_at カラム
  - ハッシュによる重複チェッククエリ
  - 新規ハッシュの登録機能
  - _Requirements: 3.6_

- [x] 7. 画像ダウンロード・保存サービス
- [x] 7.1 ImageStorageService の基本機能を実装
  - httpx.AsyncClient を使用した非同期ダウンロード
  - タイムアウト設定（connect=5s, read=30s）
  - 3回リトライ（exponential backoff）
  - calculate_hash() で SHA-256 ハッシュ計算
  - validate_image_format() で MIME タイプ検証（JPEG, PNG, GIF, WebP）
  - _Requirements: 3.1, 3.4, 3.5, 3.8_

- [x] 7.2 ImageStorageService の download_and_store() を実装
  - 複数画像の並列ダウンロード処理
  - check_duplicate() による重複スキップ
  - 成功/失敗の ImageDownloadResult リストを返却
  - 失敗時はログ記録し元 URL を保持して継続
  - _Requirements: 3.1, 3.3, 3.4, 3.5, 3.6_

- [x] 7.3 ImageStorageService の監視機能を実装
  - get_failure_rate() でダウンロード失敗率を算出
  - get_storage_usage_bytes() でストレージ使用量を取得
  - 失敗率カウンターの管理
  - _Requirements: 6.2, 6.4_

- [x] 8. 画像永続化の統合
- [x] 8.1 AnimalRepository に画像パス更新機能を追加
  - update_local_image_paths() メソッドを実装
  - save_animal() で ImageStorageService と連携（オプション）
  - _Requirements: 3.3_

- [x] 8.2 画像永続化のテスト
  - LocalImageStorage のユニットテスト（保存、移動、削除）
  - ImageStorageService のユニットテスト（ハッシュ計算、形式検証）
  - download_and_store() の統合テスト（モック HTTP サーバー使用）
  - 重複検出の検証
  - _Requirements: 3.1, 3.2, 3.5, 3.6, 3.8_

### Phase 4: アーカイブ・監視機能

- [x] 9. アーカイブリポジトリ
- [x] 9.1 ArchiveRepository を実装
  - get_archived_by_id() でアーカイブから取得
  - list_archived() でアーカイブデータをリスト取得（フィルタ、ページネーション対応）
  - insert_archive() でアーカイブにデータを挿入
  - 読み取り専用アクセスの強制（update/delete なし）
  - _Requirements: 2.3_

- [x] 9.2 AnimalRepository にアーカイブ対象検索機能を追加
  - find_archivable_animals() を実装（保持期間経過データを検索）
  - 保持期間の動的設定（環境変数 RETENTION_DAYS）
  - バッチ取得対応（limit パラメータ）
  - _Requirements: 2.1, 2.4_

- [x] 10. アーカイブサービス
- [x] 10.1 ArchiveService を実装
  - run_archive_job() でアーカイブ処理を実行
  - バッチ処理（1000件/バッチ）でトランザクション管理
  - 画像ファイルのアーカイブストレージへの移動
  - ArchiveJobResult で処理結果を返却
  - エラー発生時は該当バッチをスキップし次へ
  - _Requirements: 2.1, 2.2, 2.5, 3.7_

- [x] 10.2 ArchiveService のログ・通知機能を実装
  - 処理ログ（件数、時間、エラー）の記録
  - エラー発生時の運用者通知（notification-manager 連携）
  - get_archivable_count() でアーカイブ対象件数を取得
  - _Requirements: 2.6, 2.7_

- [x] 10.3 APScheduler によるアーカイブジョブ設定
  - BackgroundScheduler + SQLAlchemyJobStore の設定
  - 日次実行（毎日 02:00 JST）の cron トリガー
  - replace_existing=True で重複ジョブ防止
  - misfire_grace_time=3600 でダウンタイム後の再実行
  - _Requirements: 2.1, 2.2_

- [x] 11. 監視・メトリクス機能
- [x] 11.1 AnimalMetricsCollector を実装
  - get_status_counts() でステータス別件数を取得
  - collect() で全メトリクスを収集
  - AnimalMetrics データクラスで結果を返却
  - _Requirements: 6.1_

- [x] 11.2 generate_daily_report() を実装
  - アーカイブ対象件数
  - ストレージ使用量
  - ステータス別集計
  - 画像ダウンロード失敗率
  - _Requirements: 6.3_

- [x] 11.3 アラート機能を実装
  - 画像ダウンロード失敗率 > 10% でアラート
  - ストレージ使用量閾値超過でアラート
  - AlertManager（notification-manager パターン）との連携
  - _Requirements: 6.2, 6.4_

- [x] 11.4 監査ログ機能を実装
  - 全ステータス変更操作を監査ログに記録
  - AuditLogger（notification-manager パターン）の拡張
  - _Requirements: 6.5_

- [x] 12. アーカイブ API エンドポイント
- [x] 12.1 アーカイブデータ参照 API を実装
  - GET /archive/animals でアーカイブデータをリスト取得
  - GET /archive/animals/{id} で個別取得
  - 読み取り専用（更新・削除なし）
  - _Requirements: 2.3_

- [x] 13. Phase 4 のテスト
- [x] 13.1 ArchiveService の統合テスト
  - 完全なアーカイブフロー（データ移動 + 画像移動）の検証
  - バッチ処理とトランザクションロールバックの確認
  - エラー時のスキップ動作確認
  - _Requirements: 2.1, 2.2, 2.5, 2.6, 2.7, 3.7_

- [x] 13.2 AnimalMetricsCollector のユニットテスト
  - ステータス別集計の正確性
  - メトリクス収集の完全性
  - _Requirements: 6.1, 6.3_

- [x] 13.3 アーカイブ API の E2E テスト
  - アーカイブデータのリスト取得
  - 個別取得
  - フィルタリング（archived_from, archived_to）
  - _Requirements: 2.3_

---

## Requirements Coverage

| Requirement | Tasks |
|-------------|-------|
| 1.1 | 1.1, 2.1, 2.2, 3.2, 4.1, 5.3 |
| 1.2 | 2.2 |
| 1.3 | 1.1, 2.1, 2.2, 3.2, 4.1, 5.2 |
| 1.4 | 1.2, 2.4, 3.1, 5.2 |
| 1.5 | 1.1, 2.1, 2.2, 3.2, 4.1, 5.2 |
| 1.6 | 3.3, 4.2, 5.3 |
| 2.1 | 9.2, 10.1, 10.3 |
| 2.2 | 1.4, 10.1, 10.3, 13.1 |
| 2.3 | 1.4, 9.1, 12.1, 13.3 |
| 2.4 | 9.2 |
| 2.5 | 10.1, 13.1 |
| 2.6 | 10.2, 13.1 |
| 2.7 | 10.2, 13.1 |
| 3.1 | 6.1, 7.1, 7.2, 8.2 |
| 3.2 | 6.1, 8.2 |
| 3.3 | 1.1, 2.1, 2.2, 7.2, 8.1 |
| 3.4 | 7.1, 7.2 |
| 3.5 | 7.1, 7.2, 8.2 |
| 3.6 | 1.3, 6.2, 7.2, 8.2 |
| 3.7 | 6.1, 10.1, 13.1 |
| 3.8 | 7.1, 8.2 |
| 4.1 | (既存制約維持) |
| 4.2 | 2.3, 3.2, 4.1, 5.1, 5.3 |
| 4.3 | 2.3, 3.2, 4.1, 5.1, 5.3 |
| 4.4 | 3.2, 5.2 |
| 4.5 | 3.2, 5.2 |
| 5.1 | 2.1 |
| 5.2 | 3.3, 4.2 |
| 5.3 | 3.3, 4.2 |
| 5.4 | 4.2 |
| 5.5 | 1.1 |
| 6.1 | 11.1, 13.2 |
| 6.2 | 7.3, 11.3 |
| 6.3 | 11.2, 13.2 |
| 6.4 | 7.3, 11.3 |
| 6.5 | 11.4 |
