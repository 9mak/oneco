# Requirements Document

## Project Description (Input)
動物データをデータベースに永続化し、API経由で提供する機能

## Introduction
本仕様は、既存の data-collector で収集・正規化された保護動物データを永続化し、外部システム（公開Webポータル、通知管理、配信サービスなど）が利用できるREST API を提供する機能を定義します。これにより、動物データの一元管理と効率的なアクセスが実現され、データの統合性とアクセシビリティが向上します。

## Requirements

### Requirement 1: データベーススキーマ設計
**Objective:** As a システム管理者, I want 動物データを正規化されたスキーマでデータベースに永続化したい, so that データの整合性を保ち、効率的なクエリ実行が可能になる

#### Acceptance Criteria
1. The システム shall AnimalDataモデル（species, sex, age_months, color, size, shelter_date, location, phone, image_urls, source_url）を反映したテーブル構造を持つ
2. The システム shall 各レコードに一意識別子（primary key）を自動生成する
3. The システム shall shelter_date, species, sex, locationフィールドにインデックスを作成し、検索パフォーマンスを最適化する
4. The システム shall 全ての必須フィールド（species, shelter_date, location, source_url）に NOT NULL 制約を適用する
5. The システム shall image_urlsを配列型またはJSONB型で格納し、複数画像URLの管理を可能にする
6. The システム shall locationフィールドには詳細な保護場所情報が取得できない場合、最低限都道府県名（例: 「高知県」）を格納する

### Requirement 2: データ永続化機能
**Objective:** As a データ収集システム, I want 正規化された動物データをデータベースに保存したい, so that データの長期保存と再利用が可能になる

#### Acceptance Criteria
1. When 新しいAnimalDataオブジェクトが提供される, the システム shall データベースに新規レコードとして挿入する
2. When 既存のsource_urlと同一のデータが挿入される, the システム shall 既存レコードを更新する（upsert動作）
3. If データベース接続エラーが発生する, then the システム shall 適切なエラーメッセージをログ出力し、例外を送出する
4. If Pydanticバリデーションエラーが発生する, then the システム shall データ挿入を拒否し、バリデーションエラー詳細を返す
5. The システム shall トランザクション制御により、部分的なデータ書き込みを防止する

### Requirement 3: データ取得API
**Objective:** As a 外部システム開発者, I want REST APIを通じて動物データを取得したい, so that 公開ポータルや通知システムに統合できる

#### Acceptance Criteria
1. When GET /animals リクエストが送信される, the システム shall 全動物データのリストをJSON形式で返却する
2. When GET /animals/{id} リクエストが送信される, the システム shall 指定されたIDの動物データをJSON形式で返却する
3. If 指定されたIDのレコードが存在しない, then the システム shall HTTP 404ステータスとエラーメッセージを返却する
4. The システム shall 各APIレスポンスに適切なContent-Type（application/json）ヘッダーを設定する
5. The システム shall ISO 8601形式のタイムスタンプ（shelter_date）をJSON出力に含める
6. The システム shall 各APIレスポンスにsource_urlを含め、ユーザーが元の詳細ページに辿り着けるようにする

### Requirement 4: データフィルタリング機能
**Objective:** As a 外部システム開発者, I want クエリパラメータで動物データを絞り込みたい, so that 特定条件に合致するデータのみを効率的に取得できる

#### Acceptance Criteria
1. When GET /animals?species={動物種別} リクエストが送信される, the システム shall 指定された動物種別（犬、猫、その他）に合致するデータのみを返却する
2. When GET /animals?sex={性別} リクエストが送信される, the システム shall 指定された性別（男の子、女の子、不明）に合致するデータのみを返却する
3. When GET /animals?location={場所} リクエストが送信される, the システム shall 指定された場所（部分一致）に合致するデータのみを返却する
4. When GET /animals?shelter_date_from={日付}&shelter_date_to={日付} リクエストが送信される, the システム shall 指定期間内に収容された動物データを返却する
5. When 複数のフィルタパラメータが指定される, the システム shall AND条件で全条件に合致するデータを返却する
6. If 不正なパラメータ値が送信される, then the システム shall HTTP 400ステータスとバリデーションエラーメッセージを返却する

### Requirement 5: ページネーション対応
**Objective:** As a 外部システム開発者, I want 大量データを効率的に取得したい, so that APIレスポンスのパフォーマンスとネットワーク帯域を最適化できる

#### Acceptance Criteria
1. When GET /animals?limit={件数}&offset={オフセット} リクエストが送信される, the システム shall 指定された件数とオフセットでデータを返却する
2. The システム shall デフォルトでlimit=50, offset=0を適用する
3. The システム shall 最大limit値を1000件に制限し、超過時はHTTP 400エラーを返却する
4. The システム shall レスポンスに総レコード数（total_count）メタデータを含める
5. The システム shall ページネーション情報（current_page, total_pages, has_next）をレスポンスに含める

### Requirement 6: エラーハンドリングとロギング
**Objective:** As a システム管理者, I want 詳細なエラー情報とログを確認したい, so that 問題の迅速な診断と解決が可能になる

#### Acceptance Criteria
1. When データベースエラーが発生する, the システム shall HTTP 500ステータスと汎用エラーメッセージを返却する
2. When バリデーションエラーが発生する, the システム shall HTTP 400ステータスと具体的なエラー詳細を返却する
3. The システム shall 全APIリクエストをログ出力する（メソッド、パス、クエリパラメータ、レスポンスステータス）
4. The システム shall データベースクエリエラーを詳細ログに記録する（SQL、パラメータ、スタックトレース）
5. The システム shall 標準的なロギングフォーマット（タイムスタンプ、ログレベル、モジュール名、メッセージ）を使用する

### Requirement 7: データベース接続管理
**Objective:** As a システム管理者, I want データベース接続を効率的に管理したい, so that リソースリークを防止し、システムの安定性を確保できる

#### Acceptance Criteria
1. The システム shall コネクションプーリングを使用し、接続の再利用を可能にする
2. The システム shall 環境変数またはコンフィグファイルからデータベース接続情報（ホスト、ポート、ユーザー、パスワード、データベース名）を読み込む
3. When アプリケーション起動時, the システム shall データベース接続テストを実行し、接続失敗時は起動を中止する
4. When アプリケーション終了時, the システム shall 全てのデータベース接続を適切にクローズする
5. If コネクションプールが枯渇する, then the システム shall タイムアウトエラーをログ出力し、HTTP 503エラーを返却する

