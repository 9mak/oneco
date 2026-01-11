# Implementation Plan: data-collector

## Task Overview

以下の実装タスクは、data-collector の要件と設計に基づいて生成されています。各タスクは型安全性、エラーハンドリング、テスト容易性を重視し、段階的に機能を構築します。

**実装順序**: 基盤（Domain Layer）→ アダプター実装 → インフラストラクチャ → オーケストレーション → CLI 統合 → テスト

---

## Tasks

### 1. データモデルとバリデーション基盤の構築

- [x] 1.1 (P) 統一データモデルの実装
  - Pydantic を使用して AnimalData モデルを定義し、必須フィールド（species, shelter_date, source_url）と準必須フィールド（sex, age_months, color, size, location, phone, image_urls）を型安全に表現
  - field_validator で species ("犬", "猫", "その他")、sex ("男の子", "女の子", "不明")、age_months (負値チェック) のバリデーションを実装
  - JSON シリアライゼーション・デシリアライゼーションの動作確認（model_dump, model_dump_json）
  - _Requirements: 1.6, 2.6, 2.7_
  - _Contracts: AnimalData State_

- [x] 1.2 (P) 生データモデルの定義
  - 自治体サイトから抽出した正規化前のデータを表現する RawAnimalData モデルを Pydantic で定義
  - 全フィールドを str 型として定義し、後続の正規化処理に渡すための型安全性を確保
  - _Requirements: 1.3_
  - _Contracts: MunicipalityAdapter Service_

- [x] 1.3 データ正規化ロジックの実装
  - DataNormalizer クラスを作成し、RawAnimalData から AnimalData への変換処理を実装
  - _normalize_species: "いぬ", "DOG" → "犬"、"鳥" → "その他" などのパターンマッチング
  - _normalize_sex: "オス", "♂" → "男の子"、"?" → "不明" などの変換
  - _normalize_age: "2歳" → 24、"6ヶ月" → 6、"不明" → None の変換ロジック
  - _normalize_date: "令和8年1月5日", "2026/01/05" → "2026-01-05" の ISO 8601 変換
  - _normalize_phone: "0881234567" → "088-123-4567" のハイフン挿入
  - 不正な値に対する ValueError スロー、Pydantic の ValidationError への変換を確認
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_
  - _Contracts: DataNormalizer Service_

### 2. アダプター基盤と高知県実装

- [x] 2.1 (P) MunicipalityAdapter 抽象基底クラスの定義
  - ABC を使用して抽象基底クラス MunicipalityAdapter を定義
  - fetch_animal_list, extract_animal_details, normalize の抽象メソッドを宣言
  - prefecture_code, municipality_name の初期化ロジックを実装
  - カスタム例外クラス（NetworkError, ParsingError）を定義し、エラーハンドリングの標準化
  - _Requirements: 3.1, 3.2, 3.3, 3.6_
  - _Contracts: MunicipalityAdapter Service_

- [x] 2.2 高知県サイトの HTML 構造調査と KochiAdapter の骨組み作成
  - 高知県の保護動物情報サイト（実際の URL）の HTML 構造を手動で調査し、一覧ページと詳細ページの CSS セレクターを特定
  - KochiAdapter クラスを作成し、BASE_URL を設定、MunicipalityAdapter を継承
  - _validate_page_structure メソッドを実装し、期待される CSS セレクターの存在確認ロジックを構築
  - _Requirements: 1.1, 1.5, 3.5_
  - _Contracts: KochiAdapter Service_

- [x] 2.3 KochiAdapter の一覧ページスクレイピング実装
  - fetch_animal_list メソッドで requests を使用して一覧ページの HTML を取得
  - BeautifulSoup で一覧ページから個体詳細ページへのリンクを抽出し、絶対 URL に変換
  - _validate_page_structure で HTML 構造検証を実施し、構造変更時は ParsingError をスロー
  - HTTP エラー時の NetworkError スロー、リトライは CollectorService に委譲
  - _Requirements: 1.1, 1.2_
  - _Contracts: KochiAdapter Service_

- [x] 2.4 KochiAdapter の詳細ページスクレイピング実装
  - extract_animal_details メソッドで個体詳細ページの HTML を取得
  - BeautifulSoup で動物種別、性別、年齢、毛色、体格、収容日、収容場所、電話番号、画像 URL、元ページ URL を抽出
  - 画像 URL の検証（HTTP/HTTPS スキーム、拡張子チェック）、相対パスの場合は絶対 URL に変換
  - 複数画像 URL の配列化、画像が存在しない場合は空配列を設定
  - 必須フィールド欠損時は ValidationError をスロー
  - _Requirements: 1.3, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_
  - _Contracts: KochiAdapter Service_

- [x] 2.5 KochiAdapter と DataNormalizer の統合
  - normalize メソッドで DataNormalizer.normalize を呼び出し、RawAnimalData を AnimalData に変換
  - 正規化済みデータの型安全性を確認し、ValidationError のハンドリングをテスト
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_
  - _Contracts: KochiAdapter Service, DataNormalizer Service_

### 3. 差分検知とスナップショット管理

- [x] 3.1 (P) SnapshotStore の実装
  - SnapshotStore クラスを作成し、SNAPSHOT_DIR = Path("snapshots"), LATEST_SNAPSHOT_FILE = "latest.json" を定義
  - load_snapshot: latest.json を読み込み、AnimalData のリストに変換（ファイル不在時は空リスト）
  - save_snapshot: AnimalData リストを JSON としてファイルに書き込み（ensure_ascii=False, indent=2）
  - ディレクトリ自動作成、JSON パースエラー時の例外ハンドリング
  - _Requirements: 4.6_
  - _Contracts: SnapshotStore Service_

- [x] 3.2 DiffDetector の実装
  - DiffDetector クラスを作成し、DiffResult モデル（new, updated, deleted_candidates）を定義
  - detect_diff メソッドで前回スナップショットと今回データを比較
  - source_url をユニークキーとして、新規（URL 未登録）、更新（URL 既存だが内容変更）、削除候補（今回リストに不在）を分類
  - AnimalData の __eq__ による内容比較、差分情報の DiffResult への格納
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_
  - _Contracts: DiffDetector Service_

### 4. インフラストラクチャコンポーネント

- [x] 4.1 (P) OutputWriter の実装
  - OutputWriter クラスを作成し、OUTPUT_DIR = Path("output"), OUTPUT_FILE = "animals.json" を定義
  - write_output メソッドで AnimalData リストと DiffResult を JSON ファイルに出力
  - 出力形式: collected_at（ISO 8601）、total_count、diff（new_count, updated_count, deleted_count）、animals 配列
  - ディレクトリ自動作成、JSON シリアライゼーション（ensure_ascii=False, indent=2）
  - _Requirements: 2.7_
  - _Contracts: OutputWriter Service_

- [x] 4.2 (P) NotificationClient の実装
  - NotificationClient クラスを作成し、notification_config（email, slack_webhook_url 等）を環境変数から読み込み
  - send_alert メソッドで運用者にアラートを送信（NotificationLevel: INFO, WARNING, ERROR, CRITICAL）
  - notify_new_animals メソッドで新規収容動物を通知（オプション機能、Phase 2 で notification-manager に委譲予定）
  - 通知失敗時はログ記録のみで処理継続（best-effort）
  - _Requirements: 1.5_
  - _Contracts: NotificationClient Service_

### 5. 収集オーケストレーション

- [x] 5.1 CollectorService の基本構造とロックファイル管理
  - CollectorService クラスを作成し、依存コンポーネント（adapter, diff_detector, output_writer, notification_client, snapshot_store）を DI で受け取り
  - ロックファイル（.collector.lock）による重複実行防止ロジックを実装（_is_running, _acquire_lock, _release_lock）
  - finally ブロックでロックファイルのクリーンアップを保証
  - _Requirements: 6.4_
  - _Contracts: CollectorService Service_

- [x] 5.2 CollectorService のリトライロジック実装
  - _collect_with_retry メソッドを実装し、adapter.fetch_animal_list と adapter.extract_animal_details を指数バックオフで3回リトライ
  - NetworkError 時のリトライ、ParsingError 時は即座に通知して処理スキップ
  - エラーログ記録（URL, HTTPステータスコード、タイムスタンプ）
  - _Requirements: 1.4, 5.3, 5.4_
  - _Contracts: CollectorService Service_

- [x] 5.3 CollectorService の収集フロー統合
  - run_collection メソッドで収集プロセス全体をオーケストレーション
  - 開始ログ記録（開始時刻、対象自治体、実行 ID）
  - アダプター呼び出し → 差分検知 → 出力書き込み → スナップショット保存の順序制御
  - ページ構造変更検知時の NotificationClient.send_alert 呼び出し（CRITICAL レベル）
  - 新規データあり時の NotificationClient.notify_new_animals 呼び出し
  - 完了ログ記録（終了時刻、収集件数、新規件数、エラー件数、実行時間）
  - CollectionResult（success, total_collected, new_count, updated_count, deleted_count, errors, execution_time_seconds）を返す
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 5.5, 6.3, 6.5_
  - _Contracts: CollectorService Service_

### 6. CLI とスケジューリング統合

- [x] 6.1 CLI エントリーポイントの実装
  - CLI エントリーポイント（__main__.py）を作成し、main 関数で依存コンポーネントを初期化
  - KochiAdapter, SnapshotStore, DiffDetector, OutputWriter, NotificationClient, CollectorService のインスタンス生成
  - CollectorService.run_collection を呼び出し、CollectionResult を受け取る
  - 成功時は sys.exit(0)、失敗時は sys.exit(1) で終了コード設定
  - ロギング設定（logging.basicConfig, structlog 統合）
  - _Requirements: 6.1_
  - _Contracts: CLI API_

- [x] 6.2 (P) GitHub Actions ワークフローの作成
  - .github/workflows/data-collector.yml を作成し、schedule トリガー（cron: 0 15 * * *）で毎日実行
  - workflow_dispatch トリガーで手動実行をサポート
  - Python 3.11+ セットアップ、依存関係インストール（pip install -r requirements.txt）
  - CLI 実行（python -m data_collector）、終了コード 0/1 の確認
  - シークレット環境変数（NOTIFICATION_EMAIL, SLACK_WEBHOOK_URL）の設定
  - _Requirements: 6.1, 6.2, 6.6_
  - _Contracts: GitHub Actions Scheduler_

### 7. テスト実装

- [x] 7.1 DataNormalizer のユニットテスト
  - _normalize_species のテスト: "いぬ" → "犬", "DOG" → "犬", "鳥" → "その他"
  - _normalize_sex のテスト: "オス" → "男の子", "♂" → "男の子", "?" → "不明"
  - _normalize_age のテスト: "2歳" → 24, "6ヶ月" → 6, "不明" → None
  - _normalize_date のテスト: "令和8年1月5日" → "2026-01-05", "2026/01/05" → "2026-01-05"
  - _normalize_phone のテスト: "0881234567" → "088-123-4567"
  - 不正な値に対する ValueError スローの確認
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

- [x] 7.2 AnimalData の Pydantic バリデーションテスト
  - species フィールドの3値制約テスト（"犬", "猫", "その他" のみ許可、他は ValidationError）
  - sex フィールドの3値制約テスト（"男の子", "女の子", "不明" のみ許可）
  - age_months の負値チェックテスト（v < 0 で ValidationError）
  - 必須フィールド欠損時の ValidationError スロー確認
  - JSON シリアライゼーション・デシリアライゼーションの正確性確認
  - _Requirements: 1.6, 2.6_

- [x] 7.3 DiffDetector のユニットテスト
  - 新規検知テスト: 前回スナップショットに存在しない URL を新規として識別
  - 更新検知テスト: 既存 URL の内容変更を更新として識別
  - 削除候補検知テスト: 今回リストに存在しない URL を削除候補として識別
  - 空スナップショット時の初回実行テスト（全件が新規）
  - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [x] 7.4 KochiAdapter のモック HTML 統合テスト
  - モック HTML からのリンク抽出テスト（fetch_animal_list）
  - モック詳細ページからの個体情報抽出テスト（extract_animal_details）
  - HTML 構造変更時の ParsingError スローテスト
  - 画像 URL の相対パス変換テスト、複数画像 URL の配列化テスト
  - 必須フィールド欠損時の ValidationError スローテスト
  - _Requirements: 1.1, 1.2, 1.3, 1.5, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

- [x] 7.5 CollectorService の統合テスト
  - モックアダプターを使用したエンドツーエンド収集フローテスト
  - 差分検知 + スナップショット保存の正確性確認
  - エラーハンドリング（リトライ、通知）のテスト
  - ロックファイルによる重複実行防止のテスト
  - CollectionResult の正確性確認（success, counts, errors, execution_time）
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 5.5, 6.3, 6.4, 6.5_

- [x]* 7.6 E2E テスト（オプション、実装後の検証用）
  - GitHub Actions のテスト環境での cron トリガー実行テスト
  - workflow_dispatch による手動実行テスト
  - 終了コード 0（成功）/ 1（失敗）の確認
  - 実際の高知県サイト（テスト環境）でのスクレイピング成功確認
  - 構造変更検知テスト（意図的に壊れた HTML でテスト）
  - _Requirements: 6.1, 6.2_

---

## Requirements Coverage Matrix

| Requirement | Covered by Tasks |
|-------------|------------------|
| 1.1 | 2.2, 2.3, 7.4 |
| 1.2 | 2.3, 7.4 |
| 1.3 | 1.2, 2.4, 7.4 |
| 1.4 | 5.2 |
| 1.5 | 2.2, 4.2, 7.4 |
| 1.6 | 1.1, 7.2 |
| 2.1 | 1.3, 7.1 |
| 2.2 | 1.3, 7.1 |
| 2.3 | 1.3, 7.1 |
| 2.4 | 1.3, 7.1 |
| 2.5 | 1.3, 7.1 |
| 2.6 | 1.1, 2.5, 7.2 |
| 2.7 | 1.1, 4.1 |
| 3.1 | 2.1 |
| 3.2 | 2.1 |
| 3.3 | 2.1 |
| 3.5 | 2.2 |
| 3.6 | 2.1 |
| 4.1 | 3.2, 5.3, 7.3 |
| 4.2 | 3.2, 5.3, 7.3 |
| 4.3 | 3.2, 5.3, 7.3 |
| 4.4 | 3.2, 5.3, 7.3 |
| 4.5 | 3.2, 5.3 |
| 4.6 | 3.1 |
| 5.1 | 5.3, 7.5 |
| 5.2 | 5.3, 7.5 |
| 5.3 | 5.2 |
| 5.4 | 5.2 |
| 5.5 | 5.3, 7.5 |
| 6.1 | 6.1, 7.6 |
| 6.2 | 6.2, 7.6 |
| 6.3 | 5.3, 7.5 |
| 6.4 | 5.1, 7.5 |
| 6.5 | 5.3, 7.5 |
| 6.6 | 6.2 |
| 7.1 | 2.4, 7.4 |
| 7.2 | 2.4, 7.4 |
| 7.3 | 2.4, 7.4 |
| 7.4 | 2.4, 7.4 |
| 7.5 | 2.4, 7.4 |
| 7.6 | 2.4, 7.4 |

---

_タスク生成日: 2026-01-06_
