# Requirements Document

## Project Description (Input)
data-collector: 自治体サイトから保護動物情報をスクレイピングし、統一フォーマットに正規化。高知県を第1対象とし、自治体ごとのアダプター構造で拡張性を確保。差分検知により新着情報を識別。

## Introduction

Data Collector は、自治体の保護動物情報サイトから情報を自動収集し、統一フォーマットに変換するデータ収集エンジンです。高知県を第1対象としてスタートし、将来的に他の都道府県へ拡張可能なアダプター構造を採用します。差分検知機能により新着情報を識別し、下流のコンポーネント（animal-repository）へ提供します。

## Requirements

### Requirement 1: 高知県保護動物情報の収集

**Objective:** As a システム運用者, I want 高知県の自治体サイトから保護動物情報を自動収集する機能, so that 手動での情報収集作業を削減し、毎日の情報更新を実現できる

#### Acceptance Criteria

1. When スケジュール実行トリガーが発火した, the Data Collector shall 高知県の指定された自治体サイトにアクセスする
2. When 自治体サイトのHTMLを取得した, the Data Collector shall 保護動物の一覧ページから個体情報のリンクを抽出する
3. When 個体情報ページにアクセスした, the Data Collector shall 動物種別、性別、年齢、毛色、体格、収容日、収容場所、電話番号、画像URL、元ページURLを抽出する
4. If 自治体サイトへのアクセスが失敗した, then the Data Collector shall エラーログを記録し、リトライ処理を実行する
5. If ページ構造が想定と異なる, then the Data Collector shall エラーログを記録し、システム運用者に即座に通知し、収集をスキップする
6. The Data Collector shall 収集した情報を構造化データ（JSON形式）として保持する

### Requirement 2: データの統一フォーマット正規化

**Objective:** As a 下流コンポーネント開発者, I want 自治体ごとに異なる情報形式を統一フォーマットに変換する機能, so that 自治体間の差異を吸収し、一貫したデータ処理が可能になる

#### Acceptance Criteria

1. When 自治体サイトから動物種別を抽出した, the Data Collector shall 「犬」「猫」「その他」の3値に正規化する
2. When 自治体サイトから性別を抽出した, the Data Collector shall 「男の子」「女の子」「不明」の3値に正規化する
3. When 自治体サイトから年齢を抽出した, the Data Collector shall 推定年齢を月単位の数値に変換する（例: "2歳" → 24ヶ月）
4. When 自治体サイトから収容日を抽出した, the Data Collector shall ISO 8601形式の日付（YYYY-MM-DD）に変換する
5. When 自治体サイトから電話番号を抽出した, the Data Collector shall ハイフンを含む標準形式（例: 088-XXX-XXXX）に正規化する
6. If 必須フィールド（動物種別、収容日、元ページURL）が欠損している, then the Data Collector shall そのレコードを無効としてマークし、エラーログに記録する
7. The Data Collector shall 正規化されたデータを統一スキーマ（animal-repository が期待する形式）で出力する

### Requirement 3: 自治体別アダプター構造

**Objective:** As a システム拡張担当者, I want 自治体ごとに異なるサイト構造に対応するアダプター仕組み, so that 新しい自治体の追加が容易になり、既存コードへの影響を最小化できる

#### Acceptance Criteria

1. The Data Collector shall 自治体ごとに独立したアダプタークラス/モジュールを持つ
2. Where 新しい自治体を追加する場合, the Data Collector shall 既存のアダプターインターフェースを実装することで追加できる
3. The Data Collector shall 各アダプターに必須メソッド（fetchAnimalList, extractAnimalDetails, normalize）を定義する
4. When アダプターが初期化される, the Data Collector shall 対象自治体の識別子（都道府県コード、自治体名）を設定する
5. The Data Collector shall 高知県用アダプターを第1実装として提供する
6. If アダプターの実行中にエラーが発生した, then the Data Collector shall そのアダプターのみを停止し、他の自治体の処理を継続する

### Requirement 4: 差分検知と新着識別

**Objective:** As a 通知システム開発者, I want 前回収集時からの差分を検知する機能, so that 新規収容動物や情報更新をトリガーとして下流処理（通知、RSS更新）を実行できる

#### Acceptance Criteria

1. When データ収集が完了した, the Data Collector shall 前回収集時のデータスナップショットと比較する
2. When 新しい動物個体（元ページURLが未登録）を検出した, the Data Collector shall 「新規」フラグを付与する
3. When 既存個体の情報が更新された（ステータス変更、情報修正）, the Data Collector shall 「更新」フラグと変更内容を記録する
4. When 前回存在した個体が今回のリストに含まれない, the Data Collector shall 「譲渡済み/削除」候補としてマークする
5. The Data Collector shall 差分情報（新規、更新、削除候補のリスト）を出力する
6. The Data Collector shall 今回の収集結果を次回差分検知用のスナップショットとして保存する

### Requirement 5: エラーハンドリングと可観測性

**Objective:** As a システム運用者, I want 収集プロセスの状態とエラーを監視できる機能, so that 問題の早期発見と対応が可能になる

#### Acceptance Criteria

1. When 収集処理を開始した, the Data Collector shall 開始時刻、対象自治体、実行IDをログに記録する
2. When 収集処理が完了した, the Data Collector shall 終了時刻、収集件数、新規件数、エラー件数をログに記録する
3. If ネットワークエラーが発生した, then the Data Collector shall エラー詳細（URL、HTTPステータスコード、タイムスタンプ）をログに記録する
4. If パース失敗が発生した, then the Data Collector shall 失敗したページのURL、期待された要素、実際のHTML（抜粋）をログに記録する
5. The Data Collector shall 各収集実行の結果サマリー（成功/失敗、処理時間）を構造化ログとして出力する
6. The Data Collector shall ログレベル（DEBUG、INFO、WARNING、ERROR）を適切に使い分ける

### Requirement 6: 実行スケジューリングと冪等性

**Objective:** As a システム運用者, I want 定期実行と手動実行の両方をサポートする機能, so that 毎日の自動更新と、必要に応じた即時実行が可能になる

#### Acceptance Criteria

1. The Data Collector shall コマンドライン引数またはAPI経由で手動実行可能である
2. The Data Collector shall cron互換のスケジューラーまたは外部スケジューラー（GitHub Actions等）からの実行をサポートする
3. When 同一データを複数回収集した, the Data Collector shall 重複レコードを生成せず、既存データを更新する（冪等性）
4. When 実行中に再度実行要求を受けた, the Data Collector shall 実行中であることを検出し、重複実行を防止する
5. The Data Collector shall 実行完了時のタイムスタンプを記録し、次回実行時の差分検知基準とする
6. The Data Collector shall 毎日1回（深夜または早朝）の実行を推奨設定とする

### Requirement 7: 画像データの取り扱い

**Objective:** As a フロントエンド開発者, I want 保護動物の画像URLを収集・検証する機能, so that Webサイトで動物の写真を表示できる

#### Acceptance Criteria

1. When 自治体サイトから画像URLを抽出した, the Data Collector shall 画像URLの妥当性を検証する（HTTP/HTTPSスキーム、拡張子チェック）
2. If 画像URLが相対パスの場合, then the Data Collector shall 絶対URLに変換する
3. If 画像URLにアクセスできない（404等）, then the Data Collector shall 警告ログを記録するが、データ自体は保持する
4. The Data Collector shall 複数の画像URLがある場合、すべてを配列として保持する
5. The Data Collector shall 画像URLのリストを正規化データに含める
6. If 画像が存在しない個体の場合, then the Data Collector shall 画像URLフィールドを空配列またはnullとする

---
_generated_at: 2026-01-06_
