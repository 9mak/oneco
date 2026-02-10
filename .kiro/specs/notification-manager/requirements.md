# Requirements Document

## Introduction

notification-managerは、LINE Messaging API連携による条件付き通知システムです。ユーザーが設定した通知条件（犬/猫、都道府県、年齢、サイズ、性別）に基づき、data-collectorの新着検知トリガーによって、条件にマッチする新着動物情報をLINEプッシュ通知で配信します。

現在、data-collectorは運用者向けのSlack通知のみを実装していますが（NotificationClient）、notification-managerは一般ユーザー向けのパーソナライズ通知を実現します。

### 対象ユーザー
- 保護犬・保護猫の里親希望者
- 特定条件（地域、動物特性）に合致する動物を探している一般ユーザー

### ビジネス価値
- ユーザーの希望条件に合致する動物の即時通知により、迅速なマッチングを促進
- 手動での定期的な確認負担を削減
- 新着動物の見逃しを防止

## Requirements

### Requirement 1: ユーザー登録と通知条件設定

**Objective:** As a 里親希望者, I want LINE上で通知条件を登録・管理できる機能, so that 自分の希望に合った動物の情報だけを受け取れる

#### Acceptance Criteria
1. When ユーザーがLINE友だち追加を行う, the Notification Manager shall ユーザー識別子を生成し、初期登録状態を作成する
2. When ユーザーが通知条件設定コマンドを送信する, the Notification Manager shall 対話形式で条件入力フローを開始する
3. The Notification Manager shall 以下の条件項目を設定可能にする:
   - 動物種別（犬/猫/両方）
   - 都道府県（複数選択可）
   - 年齢範囲（推定年齢）
   - サイズ（小型/中型/大型）
   - 性別（オス/メス/不問）
4. When ユーザーが条件設定を完了する, the Notification Manager shall 設定内容をデータベースに永続化し、確認メッセージを送信する
5. When ユーザーが条件変更コマンドを送信する, the Notification Manager shall 既存条件を表示し、変更フローを開始する
6. When ユーザーが通知停止コマンドを送信する, the Notification Manager shall 通知を無効化し（データは保持）、停止確認メッセージを送信する
7. When ユーザーが通知再開コマンドを送信する, the Notification Manager shall 通知を有効化し、再開確認メッセージを送信する

### Requirement 2: data-collectorとの連携

**Objective:** As a システム, I want data-collectorの新着検知イベントを受け取る機能, so that リアルタイムで新着動物を通知できる

#### Acceptance Criteria
1. The Notification Manager shall data-collectorからの新着動物通知を受け取るAPIエンドポイントを提供する
2. When data-collectorが新着動物を検知する, the Notification Manager shall 新着動物データ（AnimalData形式）を受信し、処理キューに追加する
3. The Notification Manager shall 受信した新着動物データのバリデーションを実行する
4. If 新着動物データが不正な場合, then the Notification Manager shall エラーログを記録し、HTTPエラーレスポンスを返す
5. When 新着動物データが正常に受信された場合, the Notification Manager shall HTTP 202（Accepted）レスポンスを返し、非同期処理を開始する

### Requirement 3: 条件マッチング処理

**Objective:** As a システム, I want 新着動物とユーザー条件を照合する機能, so that 条件に合致するユーザーにのみ通知できる

#### Acceptance Criteria
1. When 新着動物データを受信した場合, the Notification Manager shall すべてのアクティブなユーザー通知条件を取得する
2. The Notification Manager shall 各ユーザー条件と新着動物データの照合を実行する:
   - 動物種別の一致確認
   - 都道府県の一致確認
   - 年齢範囲の包含確認
   - サイズの一致確認
   - 性別の一致確認
3. When すべての設定条件が一致する場合, the Notification Manager shall 該当ユーザーを通知対象リストに追加する
4. When いずれかの条件が不一致の場合, the Notification Manager shall 該当ユーザーを通知対象から除外する
5. The Notification Manager shall マッチング結果をログに記録する（マッチ数、除外数）

### Requirement 4: LINE通知配信

**Objective:** As a システム, I want 条件に合致したユーザーにLINE通知を送信する機能, so that 新着情報を即座に届けられる

#### Acceptance Criteria
1. When 通知対象ユーザーが特定された場合, the Notification Manager shall 各ユーザーにLINE Messaging APIを使用してプッシュメッセージを送信する
2. The Notification Manager shall 通知メッセージに以下の情報を含める:
   - 動物種別
   - 性別
   - 推定年齢
   - サイズ
   - 収容地域（都道府県・市区町村）
   - 元ページURL
3. The Notification Manager shall 通知送信結果（成功/失敗）をログに記録する
4. If LINE APIからエラーレスポンスを受信した場合, then the Notification Manager shall エラー内容をログに記録し、リトライ処理を実行する（最大3回）
5. If リトライ後も失敗する場合, then the Notification Manager shall 失敗通知を運用者に送信し、処理を継続する
6. The Notification Manager shall レート制限を遵守し、LINE APIの送信上限を超えないように制御する

### Requirement 5: 通知履歴管理

**Objective:** As a システム, I want 通知送信履歴を記録・管理する機能, so that 重複通知を防止し、監査証跡を残せる

#### Acceptance Criteria
1. When 通知を送信した場合, the Notification Manager shall 以下の情報を履歴として記録する:
   - ユーザー識別子
   - 動物データID
   - 送信日時
   - 送信結果（成功/失敗）
2. When 新着動物の通知処理を開始する場合, the Notification Manager shall 各ユーザーへの過去通知履歴を確認する
3. If 同一動物データがすでに通知済みの場合, then the Notification Manager shall 該当ユーザーへの通知をスキップする
4. The Notification Manager shall 通知履歴を少なくとも90日間保持する
5. The Notification Manager shall 90日を超過した通知履歴を自動的にアーカイブまたは削除する

### Requirement 6: エラーハンドリングと監視

**Objective:** As a 運用者, I want システムエラーと異常状態を検知・通知する機能, so that 問題を迅速に把握し対応できる

#### Acceptance Criteria
1. If data-collectorからのAPI呼び出しが認証エラーの場合, then the Notification Manager shall エラーログを記録し、HTTP 401を返す
2. If データベース接続エラーが発生した場合, then the Notification Manager shall エラーログを記録し、運用者に通知する
3. If LINE API接続エラーが発生した場合, then the Notification Manager shall エラーログを記録し、リトライ処理を実行する
4. The Notification Manager shall 以下のメトリクスを記録する:
   - 1時間あたりの通知送信数
   - API応答時間
   - エラー発生率
5. When メトリクスが閾値を超えた場合, the Notification Manager shall 運用者にアラート通知を送信する
6. The Notification Manager shall ヘルスチェックエンドポイント（`/health`）を提供し、サービス状態を返す

### Requirement 7: セキュリティとプライバシー

**Objective:** As a システム, I want ユーザーデータを安全に管理する機能, so that プライバシーを保護し、不正アクセスを防止できる

#### Acceptance Criteria
1. The Notification Manager shall LINE ユーザーIDを暗号化してデータベースに保存する
2. The Notification Manager shall data-collectorからのAPI呼び出しに対してAPIキー認証を要求する
3. If 無効なAPIキーを受信した場合, then the Notification Manager shall HTTP 401を返し、アクセスをログに記録する
4. The Notification Manager shall すべてのAPI通信にHTTPSを使用する
5. When ユーザーがブロック・友だち削除を行った場合, the Notification Manager shall 該当ユーザーの通知条件を無効化する
6. The Notification Manager shall 個人データへのアクセスをログに記録し、監査証跡を残す

### Requirement 8: スケーラビリティとパフォーマンス

**Objective:** As a システム, I want 大量通知を効率的に処理する機能, so that ユーザー増加に対応できる

#### Acceptance Criteria
1. The Notification Manager shall 新着動物データの受信と通知送信を非同期処理で実行する
2. When 大量の通知対象ユーザーが存在する場合, the Notification Manager shall バッチ処理で通知を送信する（バッチサイズ: 100件/バッチ）
3. The Notification Manager shall 並列処理により複数の通知を同時送信する（最大同時実行数: 10）
4. The Notification Manager shall 通知処理の平均応答時間が5秒以内であることを保証する
5. When データベース接続プールが枯渇した場合, the Notification Manager shall 新規リクエストをキューに追加し、順次処理する

