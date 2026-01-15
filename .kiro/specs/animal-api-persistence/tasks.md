# Implementation Plan: animal-api-persistence

## Task Overview

以下の実装タスクは、animal-api-persistence の要件と設計に基づいて生成されています。各タスクは型安全性、エラーハンドリング、テスト容易性を重視し、段階的に機能を構築します。

**実装順序**: 基盤（Database Layer）→ Repository実装 → API実装 → 統合 → テスト

---

## Tasks

### 1. データベース基盤の構築

- [x] 1.1 (P) SQLAlchemyモデルの定義
  - AnimalテーブルのSQLAlchemyモデルクラスを作成し、全フィールド（id, species, sex, age_months, color, size, shelter_date, location, phone, image_urls, source_url）を定義
  - JSONB型でimage_urlsを格納し、PostgreSQLのJSONBサポートを活用
  - 必須フィールド（species, shelter_date, location, source_url）にNOT NULL制約を適用
  - source_urlにUNIQUE制約を設定し、重複データの挿入を防止
  - デフォルト値を設定（sex='不明', image_urls=[]）
  - _Requirements: 1.1, 1.2, 1.4, 1.5_
  - _Contracts: Animal Table Schema_

- [x] 1.2 (P) データベースインデックスの定義
  - species, sex, shelter_date, locationフィールドに個別インデックスを作成
  - 複合検索用の複合インデックス（species, sex, location）を定義
  - source_urlのユニークインデックスを設定
  - インデックス定義をSQLAlchemyモデルに統合
  - _Requirements: 1.3_
  - _Contracts: Animal Table Schema_

- [x] 1.3 (P) データベース接続管理の実装
  - pydantic-settingsでDatabaseSettingsクラスを作成し、環境変数（DATABASE_URL, DB_POOL_SIZE, DB_MAX_OVERFLOW）を読み込み
  - SQLAlchemyのcreate_async_engineでコネクションプールを作成
  - async_sessionmakerでセッションファクトリを設定
  - get_session()メソッドでAsyncSessionを提供し、コンテキストマネージャーで自動クローズを保証
  - close()メソッドでエンジンのdisposeを実行
  - _Requirements: 7.1, 7.2, 7.4_
  - _Contracts: DatabaseConnection Service_

- [x] 1.4 (P) Alembicマイグレーション環境の初期化
  - alembic initでマイグレーション環境を作成
  - env.pyでasync engineを設定し、非同期マイグレーションをサポート
  - alembic.iniでデータベースURLを環境変数から読み込み
  - マイグレーションスクリプトテンプレートを確認
  - _Requirements: 7.2_

- [x] 1.5 初期マイグレーションの作成と実行
  - alembic revision --autogenerate でanimalsテーブル作成マイグレーションを生成
  - マイグレーションスクリプトを検証し、インデックスと制約が正しく定義されているか確認
  - alembic upgradeでマイグレーションを実行し、テーブルを作成
  - ロールバックテスト（alembic downgrade → alembic upgrade）を実行
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

### 2. Repositoryパターンの実装

- [x] 2.1 (P) AnimalRepositoryの基本構造
  - AnimalRepositoryクラスを作成し、AsyncSessionを依存注入で受け取る
  - 既存のPydantic AnimalDataモデルをインポートし、SQLAlchemyモデルとの変換を準備
  - Pydantic AnimalDataとSQLAlchemy Animalモデルの相互変換ヘルパーメソッドを実装
  - _Requirements: 2.1_
  - _Contracts: AnimalRepository Service_

- [x] 2.2 データ保存機能（upsert）の実装
  - save_animal()メソッドで、AnimalDataをSQLAlchemy Animalモデルに変換
  - source_urlでSELECTし、既存レコードがあればUPDATE、なければINSERTを実行
  - トランザクションをコミットし、保存後のデータをAnimalDataとして返却
  - データベースエラー時はDatabaseErrorを送出
  - Pydanticバリデーションエラーを適切にハンドリング
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_
  - _Contracts: AnimalRepository Service_

- [x] 2.3 (P) ID指定データ取得機能の実装
  - get_animal_by_id()メソッドで、指定されたIDのレコードをSELECT
  - 存在する場合はAnimalDataに変換して返却、存在しない場合はNoneを返却
  - _Requirements: 3.2, 3.3_
  - _Contracts: AnimalRepository Service_

- [x] 2.4 (P) リスト取得・フィルタリング機能の実装
  - list_animals()メソッドで、species, sex, location, shelter_date_from, shelter_date_toのフィルタパラメータを受け取る
  - WHERE句で各フィルタを適用（locationは部分一致LIKE検索）
  - 複数フィルタはAND条件で結合
  - フィルタパラメータのバリデーション（不正値チェック）を実装
  - ORDER BY shelter_date DESCでソート
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_
  - _Contracts: AnimalRepository Service_

- [x] 2.5 ページネーション機能の実装
  - list_animals()でlimitとoffsetパラメータを受け取る
  - デフォルト値（limit=50, offset=0）を設定
  - limitの最大値を1000に制限
  - LIMITとOFFSET句をクエリに適用
  - 総レコード数をCOUNTクエリで取得し、タプル（List[AnimalData], int）として返却
  - ページネーションメタデータ（current_page, total_pages, has_next）を計算
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_
  - _Contracts: AnimalRepository Service_

### 3. FastAPI アプリケーションの実装

- [x] 3.1 (P) API スキーマの定義
  - AnimalPublicスキーマを作成し、全フィールド（id, species, sex, age_months, color, size, shelter_date, location, phone, image_urls, source_url）を定義
  - from_attributes=Trueを設定し、SQLAlchemyモデルからの変換をサポート
  - PaginationMetaスキーマを作成し、total_count, limit, offset, current_page, total_pages, has_nextを定義
  - PaginatedResponseジェネリックスキーマを作成し、itemsとmetaを含める
  - ISO 8601形式の日付シリアライゼーションを確認
  - _Requirements: 3.4, 3.5, 3.6, 5.4, 5.5_
  - _Contracts: API Schemas State_

- [x] 3.2 (P) FastAPIアプリケーションの初期化
  - FastAPIインスタンスを作成し、タイトル、説明、バージョンを設定
  - CORSMiddlewareを追加し、環境変数から許可オリジンを読み込み
  - DatabaseConnectionをシングルトンとして初期化
  - startup/shutdownイベントでデータベース接続テストと接続クローズを実行
  - _Requirements: 3.4, 7.3, 7.4_
  - _Contracts: FastAPI Application API_

- [x] 3.3 (P) 依存性注入の設定
  - get_session依存性を定義し、DatabaseConnection.get_session()を呼び出す
  - SessionDepタイプエイリアスを定義（Annotated[AsyncSession, Depends(get_session)]）
  - 依存関数をテスト用にオーバーライド可能にする
  - _Requirements: 7.1_

- [x] 3.4 動物リスト取得エンドポイントの実装
  - GET /animalsエンドポイントを定義し、Queryパラメータでspecies, sex, location, shelter_date_from, shelter_date_to, limit, offsetを受け取る
  - limitの最大値を1000に制限（Query(le=1000, ge=1)）、offsetは0以上（Query(ge=0)）
  - AnimalRepository.list_animals()を呼び出し、結果をPaginatedResponse[AnimalPublic]として返却
  - PaginationMetaを計算（current_page, total_pages, has_next）
  - バリデーションエラー時にHTTP 400を返却
  - _Requirements: 3.1, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 5.1, 5.2, 5.3_
  - _Contracts: API Routes API_

- [x] 3.5 動物個別取得エンドポイントの実装
  - GET /animals/{animal_id}エンドポイントを定義し、Pathパラメータでanimal_idを受け取る
  - AnimalRepository.get_animal_by_id()を呼び出し、結果が存在すればAnimalPublicとして返却
  - 存在しない場合はHTTP 404エラーを返却
  - _Requirements: 3.2, 3.3_
  - _Contracts: API Routes API_

- [x] 3.6 (P) エラーハンドラーの実装
  - HTTPExceptionハンドラーを登録し、detail, errorsフィールドを含むJSONレスポンスを返却
  - RequestValidationErrorハンドラーを登録し、Pydanticバリデーションエラーをフィールド別に整形
  - データベースエラー時はHTTP 500を返却し、詳細はログのみに記録
  - エラーレスポンス形式を統一
  - _Requirements: 6.1, 6.2_

- [x] 3.7 (P) ロギング設定
  - structlogまたは標準loggingモジュールで構造化ロギングを設定
  - 全APIリクエストをログ出力（メソッド, パス, クエリパラメータ, ステータスコード, レスポンスタイム）
  - データベースエラーをERRORレベルでログ出力（SQL, パラメータ, スタックトレース）
  - ログフォーマット（タイムスタンプ, ログレベル, モジュール名, メッセージ）を設定
  - _Requirements: 6.3, 6.4, 6.5_

### 4. 既存システムとの統合

- [x] 4.1 AnimalDataモデルのlocationフィールド必須化
  - src/data_collector/domain/models.pyのAnimalDataを修正
  - location: Optional[str]をlocation: strに変更
  - デフォルト値なしで必須フィールド化
  - _Requirements: 1.4, 1.6_

- [x] 4.2 KochiAdapterのlocationフォールバック実装
  - KochiAdapterでlocationが取得できない場合に「高知県」をフォールバック値として設定
  - 他の自治体アダプターも同様にフォールバック処理を追加
  - location取得失敗時のログ出力を追加
  - _Requirements: 1.6_

- [x] 4.3 CollectorServiceへのRepository統合
  - CollectorServiceのコンストラクタでAnimalRepositoryを依存注入で受け取る
  - run_collection()メソッドで、収集後にAnimalRepository.save_animal()を呼び出し、データベースに永続化
  - 既存のOutputWriter（JSON出力）は当面併用
  - データベースエラー時はNotificationClient.send_alert()でアラート送信
  - データベースエラーをログに記録
  - _Requirements: 2.1, 2.2, 2.3_

- [x] 4.4 CLIエントリーポイントの更新
  - __main__.pyでDatabaseConnectionを初期化
  - AnimalRepositoryをインスタンス化し、CollectorServiceに注入
  - アプリケーション終了時にDatabaseConnection.close()を呼び出す
  - _Requirements: 7.4_

### 5. テスト実装

- [x] 5.1 (P) DatabaseConnectionのユニットテスト
  - get_session()のセッション生成とクローズを確認
  - 接続エラー時の例外ハンドリングを確認
  - テスト用データベース（SQLite in-memory）を使用
  - _Requirements: 7.1, 7.3_
  - _Test File: tests/test_database_connection.py (6 tests)_

- [x] 5.2 (P) Repositoryユニットテストの実装
  - pytest + pytest-asyncioでテスト環境を構築
  - SQLite in-memoryデータベースでテスト用セッションを作成
  - save_animal()のupsertロジックテスト（新規挿入、既存更新）
  - get_animal_by_id()のテスト（存在する場合、存在しない場合）
  - list_animals()のフィルタリングテスト（species, sex, location, 日付範囲）
  - list_animals()のページネーションテスト（limit, offset, 総件数）
  - バリデーションエラーのハンドリングを確認
  - _Requirements: 2.1, 2.2, 3.2, 3.3, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 5.1, 5.2, 5.4_
  - _Test File: tests/test_animal_repository.py (10 tests)_

- [x] 5.3 (P) API統合テストの実装
  - httpx.AsyncClientでFastAPIアプリケーションをテスト
  - GET /animalsエンドポイントのテスト（フィルタリング、ページネーション、レスポンス形式）
  - GET /animals/{id}エンドポイントのテスト（存在する場合、404エラー）
  - バリデーションエラーのテスト（不正なlimit値、不正な日付形式）
  - TestClient（httpx）を使用し、テスト用データベースを使用
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 5.1, 5.2, 5.3, 5.4, 5.5, 6.1, 6.2_
  - _Test File: tests/test_api_routes.py (13 tests)_

- [x] 5.4 CollectorService統合テストの実装
  - モックアダプターでデータを収集し、AnimalRepositoryに永続化
  - データベースからデータを取得し、正しく保存されているか検証
  - upsert動作（既存データの更新）を確認
  - データベースエラー時のアラート送信テスト
  - データベースエラー時のログ出力を確認
  - _Requirements: 2.1, 2.2, 2.3, 2.4_
  - _Test File: tests/orchestration/test_collector_service.py (18 tests)_

- [x] 5.5 (P) データベースマイグレーションテストの実装
  - テスト用PostgreSQLコンテナでマイグレーションを実行
  - テーブル、インデックス、制約の存在確認
  - ロールバックテストを実行し、データ整合性を検証
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_
  - _Test File: tests/test_migration.py (5 tests)_

- [x] 5.6 (P) パフォーマンステストの実装
  - 1000件のupsert操作のパフォーマンステスト（< 10秒）
  - 複数フィルタ条件でのクエリパフォーマンステスト（< 100ms）
  - 大量データ（10,000件）でのページネーションテスト（offset=9000でも< 200ms）
  - 同時接続数（50リクエスト）の負荷テスト
  - locustまたはpytest-benchmarkを使用
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 5.1, 5.2_
  - _Test File: tests/test_performance.py (5 tests)_

### 6. ヘルスチェックとエンドツーエンド検証

- [x] 6.1 (P) ヘルスチェックエンドポイントの実装
  - GET /healthエンドポイントを定義
  - データベース接続テストを実行し、成功時は200、失敗時は503を返却
  - レスポンスにstatus（"healthy" / "unhealthy"）とtimestampを含める
  - _Requirements: 7.3_

- [x] 6.2 エンドツーエンドテスト
  - data-collectorでデータ収集 → データベース永続化 → API取得の一連の流れを確認
  - 実際の高知県サイトからデータを収集してデータベースに保存
  - API経由でデータを取得し、正しく返却されることを確認
  - _Requirements: 2.1, 3.1, 3.2_
  - _Test File: tests/test_e2e.py (7 tests)_

- [x] 6.3 (P) ドキュメント生成とAPI確認
  - FastAPIの自動生成ドキュメント（/docs, /openapi.json）を確認
  - 各エンドポイントの説明、パラメータ、レスポンススキーマが正しく表示されることを確認
  - _Requirements: 3.4_
  - _Test File: tests/test_openapi_docs.py (12 tests)_

- [x] 6.4 エラーハンドリングとログ検証
  - 各種エラーケース（404, 400, 500）のレスポンスとログを確認
  - ログフォーマット（タイムスタンプ、ログレベル、モジュール名）を検証
  - データベースエラー時のスタックトレース記録を確認
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_
  - _Test Files: tests/test_error_handlers.py (4 tests), tests/test_logging.py (3 tests)_

---

## Requirements Coverage Matrix

| Requirement | Covered by Tasks |
|-------------|------------------|
| 1.1 | 1.1, 1.5 |
| 1.2 | 1.1, 1.5 |
| 1.3 | 1.2, 1.5 |
| 1.4 | 1.1, 1.5, 4.1 |
| 1.5 | 1.1, 1.5 |
| 1.6 | 4.1, 4.2 |
| 2.1 | 2.1, 2.2, 4.3, 5.2, 5.4, 6.2 |
| 2.2 | 2.2, 4.3, 5.2, 5.4 |
| 2.3 | 2.2, 4.3, 5.4 |
| 2.4 | 2.2, 5.4 |
| 2.5 | 2.2 |
| 3.1 | 3.4, 5.3, 6.2 |
| 3.2 | 2.3, 3.5, 5.2, 5.3, 6.2 |
| 3.3 | 2.3, 3.5, 5.2, 5.3 |
| 3.4 | 3.1, 3.2, 5.3, 6.3 |
| 3.5 | 3.1, 5.3 |
| 3.6 | 3.1, 5.3 |
| 4.1 | 2.4, 3.4, 5.2, 5.3, 5.6 |
| 4.2 | 2.4, 3.4, 5.2, 5.3, 5.6 |
| 4.3 | 2.4, 3.4, 5.2, 5.3, 5.6 |
| 4.4 | 2.4, 3.4, 5.2, 5.3, 5.6 |
| 4.5 | 2.4, 3.4, 5.3 |
| 4.6 | 2.4, 3.4, 5.3 |
| 5.1 | 2.5, 3.4, 5.2, 5.3, 5.6 |
| 5.2 | 2.5, 3.4, 5.2, 5.3, 5.6 |
| 5.3 | 2.5, 3.4, 5.3 |
| 5.4 | 2.5, 3.1, 5.2, 5.3 |
| 5.5 | 2.5, 3.1, 5.3 |
| 6.1 | 3.6, 5.3, 6.4 |
| 6.2 | 3.6, 5.3, 6.4 |
| 6.3 | 3.7, 6.4 |
| 6.4 | 3.7, 6.4 |
| 6.5 | 3.7, 6.4 |
| 7.1 | 1.3, 3.3, 5.1 |
| 7.2 | 1.3, 1.4 |
| 7.3 | 3.2, 5.1, 6.1 |
| 7.4 | 1.3, 3.2, 4.4 |

---

_タスク生成日: 2026-01-14_
