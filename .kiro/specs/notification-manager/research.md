# 調査・設計決定ログ

---
**目的**: notification-manager の技術設計を裏付ける調査結果、アーキテクチャ検討、設計根拠を記録する。
---

## 概要
- **機能**: notification-manager
- **ディスカバリースコープ**: Complex Integration（新機能 + 外部API連携 + データベース設計 + 非同期処理）
- **主要な調査結果**:
  - LINE Messaging API Python SDK v3.x を使用し、プッシュ通知を実装可能
  - 既存のアーキテクチャ（FastAPI + SQLAlchemy async + Repository pattern）に準拠
  - 初期段階では FastAPI BackgroundTasks を使用し、将来的にタスクキュー（Celery/Dramatiq）へ拡張可能な設計

## 調査ログ

### LINE Messaging API 調査

**背景**: ユーザーへのLINE通知配信に必要なAPI仕様とPython SDKの調査

**参照したソース**:
- [LINE Developers - Send messages](https://developers.line.biz/en/docs/messaging-api/sending-messages/)
- [LINE Developers - Messaging API reference](https://developers.line.biz/en/reference/messaging-api/)
- [GitHub - line/line-bot-sdk-python](https://github.com/line/line-bot-sdk-python)
- [PyPI - line-bot-sdk](https://pypi.org/project/line-bot-sdk/)

**調査結果**:
- **公式Python SDK**: `line-bot-sdk` v3.x が利用可能（v2.x とは互換性なし）
- **認証方式**: Bearer トークン認証（`Authorization: Bearer {channel_access_token}`）
- **エンドポイント**: `POST https://api.line.me/v2/bot/message/push`
- **メッセージ制限**: 1リクエストあたり最大5つのメッセージオブジェクト、送信数のカウントは受信者数ベース
- **メッセージタイプ**: テキスト、スタンプ、画像、動画、音声、位置情報、Flex Message など
- **レート制限**: 月次メッセージ制限あり、クォータ超過時は配信失敗
- **エラーハンドリング**: HTTPステータスコードによるエラー応答、リトライ推奨

**設計への影響**:
- LINE SDK v3.x を依存関係に追加
- Channel Access Token を環境変数で管理（セキュリティ）
- 送信失敗時のリトライロジック実装（最大3回）
- レート制限遵守のため、送信数モニタリングとスロットリング機構が必要
- メッセージフォーマットは Flex Message ではなくシンプルなテキストメッセージで開始

### 非同期タスク処理アーキテクチャ

**背景**: data-collectorからのWebhook受信後、通知処理を非同期で実行する必要がある

**参照したソース**:
- [FastAPI - Background Tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/)
- [Medium - Celery and Background Tasks with FastAPI](https://medium.com/@hitorunajp/celery-and-background-tasks-aebb234cae5d)
- [UnfoldAI - FastAPI and Background Tasks](https://unfoldai.com/fastapi-background-tasks/)
- [DevPro Portal - Python Background Tasks 2025](https://devproportal.com/languages/python/python-background-tasks-celery-rq-dramatiq-comparison-2025/)

**調査結果**:
- **FastAPI BackgroundTasks**: 軽量タスク向け、同一プロセス内で実行、永続化なし、リトライなし
- **Celery**: エンタープライズグレード、複雑なワークフロー対応、分散処理、高スケーラビリティ
- **Dramatiq**: Celeryよりシンプル、メッセージ信頼性重視、RabbitMQ推奨
- **RQ**: 最もシンプル、Redis依存、小規模アプリ向け

**選定基準**:
- 初期段階のユーザー数は少数（数十〜数百件）
- 通知マッチング処理は軽量（メモリ内で完結）
- LINE API呼び出しは外部I/O（非同期処理に適している）

**設計への影響**:
- Phase 1（MVP）: FastAPI BackgroundTasks を使用
  - HTTP 202 Accepted で即座にレスポンスを返す
  - バックグラウンドタスクで通知マッチング・配信を実行
  - シンプルで追加の依存関係なし
- Phase 2（スケーラビリティ改善時）: Celery または Dramatiq へ移行
  - タスクキュー（Redis/RabbitMQ）導入
  - リトライ・優先度制御・分散処理が可能
  - 移行時はアダプターパターンで実装を隠蔽

### 条件マッチングエンジン設計

**背景**: ユーザー条件と新着動物データの照合ロジックの設計

**参照したソース**:
- [TutorialsPoint - Filter Pattern](https://www.tutorialspoint.com/design_pattern/filter_pattern.htm)
- [SuprSend - Design Patterns for Notification Systems](https://www.suprsend.com/post/top-6-design-patterns-for-building-effective-notification-systems-for-developers)
- [Medium - Designing a Notification Engine](https://medium.com/@nehalmehta36/designing-a-notification-engine-a-deep-dive-into-architecture-e8593801185b)

**調査結果**:
- **Strategy Pattern**: 条件チェックロジックをカプセル化、拡張可能
- **Chain of Responsibility**: 複数の条件を順次評価、早期リターン可能
- **Filter/Criteria Pattern**: 複数のフィルタ条件を組み合わせて評価

**選定アプローチ**:
- Strategy Pattern + Criteria Pattern のハイブリッド
- 各条件項目（種別、都道府県、年齢、サイズ、性別）を独立したチェック関数として実装
- すべての条件が AND 条件でマッチする場合のみ通知対象とする
- 将来的に OR 条件や複雑なルール追加に対応できる拡張性を確保

**設計への影響**:
- `NotificationMatcher` サービスクラスを作成
- 条件チェックロジックは pure function として実装（テスタビリティ向上）
- 早期リターンによるパフォーマンス最適化（最初の不一致で即座に除外）

### データベーススキーマ設計

**背景**: ユーザー通知条件、通知履歴、処理キューのデータモデル設計

**参照したソース**:
- 既存の `src/data_collector/infrastructure/database/models.py` (Animal テーブル)
- 既存の `src/data_collector/infrastructure/database/repository.py` (Repository パターン)
- [SQLAlchemy - Asynchronous I/O](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [Leapcell - Building High-Performance Async APIs with FastAPI and SQLAlchemy 2.0](https://leapcell.io/blog/building-high-performance-async-apis-with-fastapi-sqlalchemy-2-0-and-asyncpg)

**調査結果**:
- 既存のdata-collectorは SQLAlchemy 2.0 async を使用
- Repository パターンで Pydantic ↔ SQLAlchemy の変換を実施
- PostgreSQL を本番使用、SQLite をテスト使用

**必要なテーブル**:
1. **users**: LINE ユーザー情報（user_id は暗号化）
2. **notification_preferences**: ユーザー通知条件
3. **notification_history**: 通知送信履歴（重複防止・監査証跡）
4. **notification_queue**: 非同期処理キュー（オプション、Phase 2で導入）

**設計への影響**:
- 既存の `Base` クラスを継承して新規テーブルモデルを追加
- Repository パターンを踏襲して `UserRepository`, `NotificationHistoryRepository` を実装
- LINE user_id は暗号化して保存（Fernet 対称鍵暗号化）
- 通知履歴は90日間保持、自動削除ロジックはバッチ処理で実装

### 既存システムとの統合（data-collector連携）

**背景**: data-collectorの新着検知イベントを受け取るAPI設計

**参照したソース**:
- 既存の `src/data_collector/orchestration/collector_service.py`
- 既存の `src/data_collector/infrastructure/notification_client.py`
- 既存の `src/data_collector/domain/models.py` (AnimalData)
- [FastAPI - OpenAPI Webhooks](https://fastapi.tiangolo.com/advanced/openapi-webhooks/)
- [Svix - Receive Webhooks with FastAPI](https://www.svix.com/guides/receiving/receive-webhooks-with-python-fastapi/)

**調査結果**:
- data-collector は `NotificationClient.notify_new_animals()` で新着動物を通知
- 現在はSlack通知のみ実装、notification-managerへのHTTP呼び出しに変更予定
- AnimalData 形式のデータを受信

**統合アプローチ**:
1. notification-manager は `/api/v1/notifications/webhook` エンドポイントを提供
2. data-collector は新着検知時に notification-manager の Webhook を呼び出す
3. APIキー認証で相互認証（data-collector → notification-manager）
4. Webhook は即座に HTTP 202 を返し、バックグラウンドで通知処理を実行

**設計への影響**:
- Webhook エンドポイントは AnimalData 形式のリクエストボディを受け付ける
- APIキー検証ミドルウェアを実装
- data-collector の `NotificationClient` を拡張し、HTTP POST を追加

## アーキテクチャパターン評価

既存のdata-collectorアーキテクチャおよびプロジェクトステアリング原則との整合性を考慮して評価。

| オプション | 説明 | 強み | リスク・制約 | 備考 |
|------------|------|------|--------------|------|
| **Hexagonal Architecture (採用)** | ポート&アダプター、ドメインロジックを外部依存から分離 | 明確な境界、テスタビリティ向上、外部サービス切り替え容易 | アダプター層の構築コスト | 既存のdata-collectorがこのパターンを採用しており、整合性が高い |
| Layered Architecture | プレゼンテーション層、ビジネスロジック層、データアクセス層 | シンプル、理解しやすい | 密結合になりやすい、テストが困難 | 小規模アプリには適しているが、外部API統合には不向き |
| Event-Driven Architecture | イベントソーシング、CQRS | 非同期処理に最適、スケーラビリティ高い | 複雑性増加、デバッグ困難 | 将来的な拡張として検討（Phase 2以降） |

## 設計決定

### 決定: アーキテクチャパターンとして Hexagonal Architecture を採用

**背景**: notification-manager は外部API（LINE Messaging API）、外部システム（data-collector）、データベース、非同期処理など複数の外部依存を持つ。既存のdata-collectorもHexagonalパターンを採用している。

**検討した選択肢**:
1. Hexagonal Architecture（ポート&アダプター）
2. Layered Architecture（3層アーキテクチャ）
3. Event-Driven Architecture（イベント駆動）

**選定したアプローチ**: Hexagonal Architecture

**根拠**:
- **既存パターンとの整合性**: data-collectorが既に採用しており、プロジェクト全体で一貫性を保てる
- **外部依存の分離**: LINE API、data-collector Webhook、データベースをアダプターとして実装し、ドメインロジックと分離
- **テスタビリティ**: ポートをモックすることで、外部依存なしでドメインロジックをテスト可能
- **将来の拡張性**: LINE以外の通知チャネル（Email、SMS）追加時もアダプターを追加するだけで対応可能

**トレードオフ**:
- **利点**: 明確なドメイン境界、外部依存の切り替えが容易、テストしやすい
- **欠点**: アダプター層の実装コストが増加、小規模プロジェクトでは過剰設計になる可能性

**フォローアップ**:
- ドメイン境界を明確に定義（ポート定義）
- 各アダプターの責務を明確化（LINE Adapter, Webhook Adapter, Repository Adapter）

### 決定: 非同期処理にFastAPI BackgroundTasksを使用（Phase 1）

**背景**: data-collectorからのWebhook受信後、通知マッチング・配信処理を非同期で実行する必要がある。初期段階のユーザー数は少数（数十〜数百件）。

**検討した選択肢**:
1. FastAPI BackgroundTasks
2. Celery + Redis/RabbitMQ
3. Dramatiq + RabbitMQ
4. RQ + Redis

**選定したアプローチ**: FastAPI BackgroundTasks（Phase 1）、将来的にCelery移行（Phase 2）

**根拠**:
- **シンプル性**: 追加の依存関係なし、設定不要、学習コスト低い
- **十分な性能**: 初期段階のユーザー数（〜数百件）では十分
- **迅速な開発**: タスクキューの構築・運用コストを回避してMVPを早期リリース
- **移行パス明確**: 将来的にCeleryへ移行可能な設計（アダプターパターン）

**トレードオフ**:
- **利点**: 実装がシンプル、運用コストゼロ、デバッグ容易
- **欠点**: 永続化なし（サーバー再起動でタスク消失）、リトライロジック手動実装必要、スケーラビリティ限界あり

**フォローアップ**:
- `NotificationService` をタスク実行ロジックとして実装
- 将来の移行を見据えて、タスク実行ロジックをインターフェース経由で呼び出す設計
- Phase 2でのCelery移行時は、同じインターフェースをCeleryタスクで実装

### 決定: LINE ユーザーIDの暗号化保存

**背景**: LINE ユーザーIDは個人を識別できる情報であり、プライバシー保護のため暗号化が必要（Requirement 7.1）

**検討した選択肢**:
1. 平文保存（暗号化なし）
2. ハッシュ化（SHA-256など）
3. 対称鍵暗号化（Fernet）
4. 非対称鍵暗号化（RSA）

**選定したアプローチ**: 対称鍵暗号化（Fernet）

**根拠**:
- **可逆性**: LINE APIへの通知送信時に元のuser_idが必要なため、ハッシュ化は不可
- **パフォーマンス**: 対称鍵暗号化は非対称鍵よりも高速
- **セキュリティ**: Fernet はAES 128bit + HMAC、タイムスタンプ付きで改ざん検知可能
- **Pythonサポート**: `cryptography` ライブラリで標準サポート

**トレードオフ**:
- **利点**: 可逆暗号化、高速、Pythonで簡単に実装可能
- **欠点**: 鍵管理が必要、鍵が漏洩すると全データが危険

**フォローアップ**:
- 暗号化鍵を環境変数で管理（`ENCRYPTION_KEY`）
- 鍵はランダム生成し、安全な場所に保管（AWS Secrets Manager、環境変数）
- データベースには暗号化済みのuser_idのみを保存

### 決定: 通知履歴の重複防止ロジック

**背景**: 同一動物データが複数回通知されることを防ぐ必要がある（Requirement 5.3）

**検討した選択肢**:
1. (user_id, animal_source_url) の複合ユニーク制約
2. 通知履歴テーブルでのチェックロジック
3. Redis による一時的な重複チェック

**選定したアプローチ**: (user_id, animal_source_url, notified_at::date) の複合ユニーク制約 + アプリケーションロジックでの事前チェック

**根拠**:
- **データベースレベルの保証**: ユニーク制約により確実に重複を防止
- **パフォーマンス**: インデックスによる高速チェック
- **シンプル性**: Redisなどの追加依存なし

**トレードオフ**:
- **利点**: データ整合性が保証される、追加依存なし
- **欠点**: 同一日に複数回通知が必要な場合には対応不可（現時点では不要）

**フォローアップ**:
- `notification_history` テーブルに複合ユニーク制約を追加
- 通知前にアプリケーションロジックで履歴チェックを実施（DBエラー回避）

## リスクと軽減策

### リスク1: LINE API レート制限超過による通知失敗

**軽減策**:
- 通知送信数のモニタリング（メトリクス記録）
- 1時間あたりの送信数を制限（レート制限ロジック実装）
- 閾値超過時は運用者にアラート送信

### リスク2: FastAPI BackgroundTasks のスケーラビリティ限界

**軽減策**:
- Phase 1では少数ユーザー（〜数百件）に限定してリリース
- メトリクスモニタリングでパフォーマンス劣化を検知
- Phase 2でCeleryへの移行を計画（アーキテクチャはCelery移行を考慮して設計）

### リスク3: 暗号化鍵の漏洩

**軽減策**:
- 環境変数で鍵を管理、コードには含めない
- 本番環境では AWS Secrets Manager などのシークレット管理サービスを使用
- アクセスログによる監査証跡（Requirement 7.6）

### リスク4: data-collector との API 連携失敗

**軽減策**:
- APIキー認証による相互認証
- data-collector 側でリトライロジック実装
- notification-manager 側でヘルスチェックエンドポイント提供

## 参考資料

### LINE Messaging API
- [Send messages | LINE Developers](https://developers.line.biz/en/docs/messaging-api/sending-messages/)
- [LINE Messaging API reference](https://developers.line.biz/en/reference/messaging-api/)
- [GitHub - line/line-bot-sdk-python](https://github.com/line/line-bot-sdk-python)

### FastAPI & 非同期処理
- [FastAPI - Background Tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/)
- [Async APIs with FastAPI: Patterns, Pitfalls & Best Practices](https://shiladityamajumder.medium.com/async-apis-with-fastapi-patterns-pitfalls-best-practices-2d72b2b66f25)
- [Python Background Tasks 2025: Celery vs RQ vs Dramatiq](https://devproportal.com/languages/python/python-background-tasks-celery-rq-dramatiq-comparison-2025/)

### 通知システムアーキテクチャ
- [Designing a Notification Engine: Architecture Deep Dive](https://medium.com/@nehalmehta36/designing-a-notification-engine-a-deep-dive-into-architecture-e8593801185b)
- [Notification Service Design - Ultimate Guide](https://www.notificationapi.com/blog/notification-service-design-with-architectural-diagrams)
- [Design Patterns for Notification Systems](https://www.suprsend.com/post/top-6-design-patterns-for-building-effective-notification-systems-for-developers)

### SQLAlchemy Async
- [Asynchronous I/O (asyncio) — SQLAlchemy 2.0](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [Building High-Performance Async APIs with FastAPI, SQLAlchemy 2.0](https://leapcell.io/blog/building-high-performance-async-apis-with-fastapi-sqlalchemy-2-0-and-asyncpg)
