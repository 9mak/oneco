# Research & Design Decisions: animal-repository

---
**Purpose**: animal-repository 設計のための調査結果とアーキテクチャ決定を記録
**Updated**: 2026-01-27
---

## Summary

- **Feature**: animal-repository
- **Discovery Scope**: Extension（既存 animal-api-persistence の拡張）
- **Key Findings**:
  1. APScheduler + SQLAlchemy JobStore がバックグラウンドジョブに最適（PostgreSQL 対応、AsyncScheduler サポート）
  2. 画像重複検出は SHA-256 コンテンツハッシュが最もシンプルかつ堅牢（完全一致検出）
  3. アーカイブ戦略は「物理移動（別テーブル）」を採用（クエリパフォーマンス、ストレージ分離）

## Research Log

### スケジューラー選定

- **Context**: アーカイブジョブ（日次）、日次レポート生成に必要
- **Sources Consulted**:
  - [APScheduler Documentation](https://apscheduler.readthedocs.io/en/master/userguide.html)
  - [Better Stack - APScheduler Guide](https://betterstack.com/community/guides/scaling-python/apscheduler-scheduled-tasks/)
  - [APScheduler SQLAlchemy JobStore](https://apscheduler.readthedocs.io/en/3.x/modules/jobstores/sqlalchemy.html)
- **Findings**:
  - APScheduler 4.x は `AsyncScheduler` をサポートし、FastAPI/asyncio と統合可能
  - `SQLAlchemyJobStore` で PostgreSQL にジョブを永続化できる
  - `replace_existing=True` + 明示的 job ID でアプリ再起動時の重複回避
  - `misfire_grace_time` 設定でダウンタイム後のジョブ処理制御
  - Celery は過剰（Redis/RabbitMQ 必須）、システム cron は移植性低下
- **Implications**:
  - APScheduler 3.x + BackgroundScheduler を採用（成熟度、既存パターンとの親和性）
  - 将来的に AsyncScheduler (4.x) への移行パスを確保
  - ジョブストアは既存 PostgreSQL を活用

### 画像ダウンロード・重複検出

- **Context**: 外部画像 URL からローカルストレージへの永続化と重複防止
- **Sources Consulted**:
  - [imagededup - GitHub](https://github.com/idealo/imagededup)
  - [aiohttp-retry - PyPI](https://pypi.org/project/aiohttp-retry/)
  - [HTTPX Async Support](https://www.python-httpx.org/async/)
- **Findings**:
  - **重複検出方式**:
    - SHA-256 コンテンツハッシュ: 完全一致検出、シンプル、高速
    - pHash (perceptual hash): ほぼ同一画像検出、Elasticsearch 必要（過剰）
    - 要件 3.6 は「重複保存防止」のため SHA-256 で十分
  - **ダウンローダー**:
    - httpx.AsyncClient: 長寿命クライアント、granular timeout サポート
    - aiohttp + aiohttp-retry: exponential backoff サポート
    - httpx を採用（プロジェクト内で aiohttp 未使用、httpx の方がシンプル）
  - **タイムアウト・リトライ**:
    - connect=5s, read=30s（画像サイズ考慮）
    - 3回リトライ、exponential backoff (2^n秒)
    - 失敗時は元 URL のみ保持し処理継続
- **Implications**:
  - `ImageStorageService` を新規作成
  - DB に `image_hash` カラム追加し、ユニーク制約で重複防止
  - ストレージパス: `storage/images/{hash[:2]}/{hash[2:4]}/{hash}.{ext}`（ハッシュベースシャーディング）

### ストレージ設計（ローカル vs S3）

- **Context**: 画像ファイルの保存先選定
- **Sources Consulted**: 既存 notification-manager のパターン、AWS S3 ドキュメント
- **Findings**:
  - 要件は「ローカルストレージ」を明示（Req 3.1）
  - 将来の S3 移行を考慮し、ストレージ抽象化層を設計
  - ディレクトリ構造: ハッシュベース（日付ベースより分散効率が良い）
- **Implications**:
  - `LocalImageStorage` クラスを実装（Protocol で抽象化）
  - 設定で `STORAGE_BASE_PATH` を環境変数化
  - アーカイブ時は `storage/archive/images/` に移動

### アーカイブ戦略

- **Context**: 譲渡後6ヶ月経過データの処理方式
- **Sources Consulted**:
  - [Soft Delete Archive Table with PostgreSQL](https://medium.com/meroxa/creating-a-soft-delete-archive-table-with-postgresql-70ba2eb6baf3)
  - [SQLAlchemy Soft Delete Techniques](https://theshubhendra.medium.com/mastering-soft-delete-advanced-sqlalchemy-techniques-4678f4738947)
  - [PostgreSQL Soft Delete Strategies](https://dev.to/oddcoder/postgresql-soft-delete-strategies-balancing-data-retention-50lo)
- **Findings**:
  - **Option A: Soft Delete (`archived_at` カラム)**
    - メリット: 実装シンプル、FK 維持
    - デメリット: 全クエリに `WHERE archived_at IS NULL` 必要、テーブル肥大化
  - **Option B: 物理移動（`animals_archive` テーブル）**
    - メリット: アクティブテーブルのクエリパフォーマンス維持、ストレージ分離可能
    - デメリット: 移動トランザクション管理、FK 考慮必要
  - **Option C: CDC (Debezium) + 外部ストレージ**
    - メリット: リアルタイム、スケーラブル
    - デメリット: インフラ複雑化（Kafka/Debezium 必要）
- **Implications**:
  - **Option B（物理移動）を採用**: アクティブデータのクエリ効率優先
  - `animals_archive` テーブルを同一スキーマ + `archived_at` カラムで作成
  - トリガーではなくアプリケーション層でトランザクション管理

### ステータス履歴保存方式

- **Context**: ステータス遷移履歴の保存方法
- **Sources Consulted**: PostgreSQL JSONB vs 正規化テーブル、既存 notification_manager パターン
- **Findings**:
  - **Option A: JSONB カラム (`status_history`)**
    - メリット: スキーマ変更不要、シンプル
    - デメリット: 履歴検索が複雑、インデックス制限
  - **Option B: 別テーブル (`animal_status_history`)**
    - メリット: 正規化、効率的なクエリ、FK 整合性
    - デメリット: テーブル増加、JOIN 必要
- **Implications**:
  - **Option B（別テーブル）を採用**: 監査要件 (6.5) を考慮し、正規化を優先
  - `animal_status_history (id, animal_id, old_status, new_status, changed_at, changed_by)`

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| 既存拡張 + 新コンポーネント | Animal/Repository 拡張 + ImageStorageService/ArchiveService 新規 | 責務分離、既存パターン踏襲 | 統合テストの複雑化 | **採用**: ハイブリッドアプローチ |
| Full Service Layer | 全機能を新サービス層に集約 | 一貫性 | 既存コードとの重複 | 過剰 |
| Domain Events | イベント駆動でステータス変更を伝播 | 疎結合 | 複雑化、notification-manager 以外では過剰 | 将来検討 |

## Design Decisions

### Decision: バックグラウンドジョブスケジューラー

- **Context**: アーカイブ処理、日次レポート生成のスケジューリング
- **Alternatives Considered**:
  1. APScheduler - Python 純正、SQLAlchemy 統合
  2. Celery - 分散タスクキュー、Redis/RabbitMQ 必要
  3. システム cron - OS 依存、移植性低
- **Selected Approach**: APScheduler 3.x + BackgroundScheduler + SQLAlchemyJobStore
- **Rationale**:
  - 既存スタック（PostgreSQL）を活用
  - 追加インフラ不要
  - notification-manager の構造と一貫性
- **Trade-offs**: 分散環境では Celery が優位だが、現時点では単一インスタンス前提
- **Follow-up**: 高負荷時の Celery 移行パスを確保

### Decision: 画像重複検出方式

- **Context**: 同一画像の重複保存防止
- **Alternatives Considered**:
  1. SHA-256 コンテンツハッシュ - 完全一致検出
  2. pHash (perceptual hash) - 類似画像検出
  3. URL ベース重複チェック - 最もシンプル
- **Selected Approach**: SHA-256 コンテンツハッシュ
- **Rationale**:
  - 要件は「重複保存防止」であり、完全一致検出で十分
  - pHash は Elasticsearch 等の追加インフラ必要
  - URL ベースは同一画像の異なる URL を検出不可
- **Trade-offs**: 類似画像（リサイズ・圧縮）は検出不可
- **Follow-up**: 必要に応じて pHash 導入を検討

### Decision: アーカイブ戦略

- **Context**: 譲渡後6ヶ月経過データの処理
- **Alternatives Considered**:
  1. Soft Delete (`archived_at` カラム)
  2. 物理移動（`animals_archive` テーブル）
  3. CDC + 外部ストレージ
- **Selected Approach**: 物理移動（別テーブル）
- **Rationale**:
  - アクティブテーブルのクエリパフォーマンス維持
  - ストレージ分離が可能（将来的にアーカイブを別 DB に）
  - 既存クエリへの影響最小化（WHERE 句追加不要）
- **Trade-offs**: 移動トランザクションの管理複雑化、FK 考慮必要
- **Follow-up**: アーカイブ復元機能の優先度確認

### Decision: HTTPクライアント選定

- **Context**: 外部画像ダウンロード用 HTTP クライアント
- **Alternatives Considered**:
  1. httpx.AsyncClient - モダン、granular timeout
  2. aiohttp - 成熟、aiohttp-retry パッケージあり
  3. requests - 同期のみ
- **Selected Approach**: httpx.AsyncClient
- **Rationale**:
  - プロジェクト内で aiohttp 未使用（依存追加最小化）
  - httpx は FastAPI と同じ作者（Starlette）で親和性高
  - granular timeout (connect/read/write) サポート
- **Trade-offs**: aiohttp-retry ほどの組み込みリトライ機能がない
- **Follow-up**: tenacity ライブラリでリトライロジック実装

## Risks & Mitigations

| Risk | Level | Mitigation |
|------|-------|------------|
| アーカイブ処理中のデータ整合性 | 高 | 行ロック + トランザクション、バッチサイズ制限（1000件/バッチ） |
| 画像ダウンロード失敗率 | 中 | リトライ (3回)、失敗時は元 URL 保持、失敗率監視 |
| ステータス遷移の不正 | 中 | ドメインモデルでバリデーション、状態遷移図に基づく検証 |
| 後方互換性の破壊 | 中 | 新フィールドは Optional、既存 API デフォルト動作維持 |
| スケジューラーの信頼性 | 低 | SQLAlchemy JobStore で永続化、misfire_grace_time 設定 |

## References

- [APScheduler Documentation](https://apscheduler.readthedocs.io/en/3.x/userguide.html) — スケジューラー設定、JobStore
- [APScheduler SQLAlchemy JobStore](https://apscheduler.readthedocs.io/en/3.x/modules/jobstores/sqlalchemy.html) — PostgreSQL 統合
- [HTTPX Async Support](https://www.python-httpx.org/async/) — 非同期 HTTP クライアント
- [imagededup](https://github.com/idealo/imagededup) — 画像重複検出ライブラリ（参考）
- [Soft Delete Archive Table with PostgreSQL](https://medium.com/meroxa/creating-a-soft-delete-archive-table-with-postgresql-70ba2eb6baf3) — アーカイブ戦略
- [SQLAlchemy Soft Delete Techniques](https://theshubhendra.medium.com/mastering-soft-delete-advanced-sqlalchemy-techniques-4678f4738947) — ソフトデリートパターン
