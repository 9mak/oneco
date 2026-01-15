# 実装ギャップ分析

## 1. 現状調査

### 既存アセット

#### プロジェクト構造
```
src/data_collector/
├── adapters/          # 自治体別スクレイピングアダプター
├── domain/            # ドメインモデルとビジネスロジック
│   ├── models.py      # RawAnimalData, AnimalData (Pydantic)
│   ├── normalizer.py  # データ正規化
│   └── diff_detector.py
├── infrastructure/    # インフラ層
│   ├── output_writer.py    # JSON出力 (output/animals.json)
│   ├── snapshot_store.py   # スナップショット管理
│   └── notification_client.py
└── orchestration/     # オーケストレーション層
    └── collector_service.py
```

#### 既存データモデル（AnimalData）
**必須フィールド:**
- `species: str` - 動物種別（3値制約: 犬、猫、その他）
- `shelter_date: date` - 収容日（ISO 8601）
- `source_url: HttpUrl` - 元ページURL

**オプショナルフィールド:**
- `sex: str` - デフォルト「不明」
- `age_months: Optional[int]`
- `color: Optional[str]`
- `size: Optional[str]`
- `location: Optional[str]` ⚠️ **要件では必須に変更**
- `phone: Optional[str]`
- `image_urls: List[HttpUrl]` - デフォルト空リスト

#### 既存の技術スタック
- **言語:** Python 3.11+
- **データバリデーション:** Pydantic 2.5.0+
- **出力形式:** JSON（ファイルベース: `output/animals.json`）
- **Webフレームワーク:** なし（CLI ベース）
- **データベース:** なし
- **テスト:** pytest

#### アーキテクチャパターン
- **レイヤードアーキテクチャ:** domain, infrastructure, orchestration の明確な分離
- **依存性注入:** CollectorService は各コンポーネントをコンストラクタで受け取る
- **ファイルベース永続化:** JSON 出力、スナップショット管理

### 既存コンポーネントの統合ポイント

**再利用可能:**
- `src/data_collector/domain/models.py::AnimalData` - データモデル（location を必須化する必要あり）
- Pydantic バリデーション機構（フィールド検証、JSON シリアライゼーション）
- レイヤードアーキテクチャパターン

**統合が必要:**
- CollectorService → データベース永続化への接続
- JSON 出力 (`output_writer.py`) → データベースへの永続化に置き換えまたは併用

### 既存の命名規約とパターン

**ディレクトリ構造:**
- `domain/` - ビジネスロジック、ドメインモデル
- `infrastructure/` - 外部システムとの接続（ストレージ、通知など）
- `orchestration/` - ユースケースの調整

**命名:**
- snake_case（Python 標準）
- クラス名: PascalCase
- サービスクラス: `*Service`, `*Client`, `*Writer`, `*Store`

**依存関係の方向:**
- orchestration → domain, infrastructure
- domain → infrastructure への依存なし（純粋なビジネスロジック）
- infrastructure → domain（モデルへの依存）

## 2. 要件実現性分析

### 技術的要求事項（要件から抽出）

#### Requirement 1: データベーススキーマ設計
**必要な技術:**
- リレーショナルデータベース（PostgreSQL推奨、理由: JSONB型サポート、配列型サポート）
- ORM または SQL ビルダー（SQLAlchemy推奨、理由: Pydantic統合、マイグレーション管理）
- マイグレーションツール（Alembic）

**ギャップ:**
- ❌ データベース接続コンポーネントが存在しない
- ❌ スキーマ定義が存在しない
- ❌ マイグレーション管理の仕組みがない

#### Requirement 2: データ永続化機能
**必要な技術:**
- データベースアクセス層（Repository パターン）
- トランザクション管理
- Upsert 操作（source_url をユニークキーとして使用）

**ギャップ:**
- ❌ Repository コンポーネントが存在しない
- ✅ AnimalData モデルは存在（Pydantic）
- ⚠️ location が Optional → 必須化が必要

#### Requirement 3-5: REST API（取得、フィルタリング、ページネーション）
**必要な技術:**
- Web フレームワーク（FastAPI 推奨、理由: Pydantic 統合、自動 API ドキュメント生成、非同期サポート）
- ルーティング、リクエストバリデーション
- クエリパラメータ処理

**ギャップ:**
- ❌ Web フレームワークが存在しない
- ❌ API エンドポイントが存在しない
- ❌ クエリビルダーが存在しない

#### Requirement 6: エラーハンドリングとロギング
**必要な技術:**
- 構造化ロギング
- HTTPエラーハンドラー

**既存アセット:**
- ✅ logging モジュール使用済み（CollectorService）
- ✅ 構造化ログパターン（extra フィールド使用）

**ギャップ:**
- ⚠️ API レイヤーのエラーハンドラーが必要

#### Requirement 7: データベース接続管理
**必要な技術:**
- コネクションプーリング
- 環境変数ベースの設定管理
- アプリケーションライフサイクル管理（起動・終了時の接続管理）

**ギャップ:**
- ❌ 接続プール管理が存在しない
- ❌ 環境変数ベースの設定がない（現在はハードコーディング）

### 実装上の制約

**既存アーキテクチャからの制約:**
- Python 3.11+ 固定（型ヒントの使用）
- Pydantic 2.x ベース（v1 との互換性なし）
- レイヤードアーキテクチャの維持が必要（domain層の純粋性）

**データモデルの制約:**
- AnimalData の location フィールドを必須化すると、既存の data-collector コードにも影響
- KochiAdapter など自治体アダプターも location のフォールバック処理が必要

**複雑性の指標:**
- **CRUD 主体:** データベースへの挿入/取得が中心
- **外部統合:** data-collector からの入力、外部システムへのAPI提供
- **ビジネスロジック:** 比較的シンプル（フィルタリング、ページネーション）

### 未解決事項（設計フェーズで調査が必要）

1. **データベース選定の確定:**
   - PostgreSQL vs SQLite vs その他
   - 開発環境での Docker 使用の有無

2. **Web フレームワークの確定:**
   - FastAPI vs Flask vs その他
   - 非同期 vs 同期の選択

3. **マイグレーション戦略:**
   - Alembic による自動マイグレーション
   - 初期スキーマの適用方法

4. **環境変数管理:**
   - python-dotenv の使用
   - 設定ファイル構造（config.py パターン）

5. **API 認証・認可:**
   - 要件に明示されていないが、公開 API として必要か？
   - API キーベース認証の検討

6. **デプロイメント:**
   - Docker コンテナ化
   - uvicorn などの ASGI サーバー選定

## 3. 実装アプローチの選択肢

### Option A: 既存コンポーネントの拡張

**戦略:**
- `src/data_collector/` 配下に新規モジュールを追加
- 既存の AnimalData モデルを API/DB 両方で共有
- infrastructure 層に database, api モジュールを追加

**具体的な変更:**

1. **models.py の拡張:**
   - `location: Optional[str]` → `location: str` に変更
   - データベース用のメタデータ追加（必要に応じて）

2. **新規ファイル追加:**
   ```
   src/data_collector/
   ├── infrastructure/
   │   ├── database/
   │   │   ├── __init__.py
   │   │   ├── connection.py      # DB接続、コネクションプール
   │   │   ├── repository.py      # AnimalRepository
   │   │   └── models.py          # SQLAlchemy/ORMモデル（必要に応じて）
   │   └── api/
   │       ├── __init__.py
   │       ├── app.py             # FastAPI アプリケーション
   │       ├── routes.py          # エンドポイント定義
   │       └── schemas.py         # API リクエスト/レスポンススキーマ
   ```

3. **CollectorService の修正:**
   - `OutputWriter` の代わりに（または併用して）`AnimalRepository` を使用
   - データベースへの永続化を追加

4. **統合ポイント:**
   - CollectorService → AnimalRepository（データ挿入）
   - FastAPI → AnimalRepository（データ取得）

**トレードオフ:**
- ✅ 既存のディレクトリ構造を維持
- ✅ AnimalData モデルの再利用
- ✅ レイヤードアーキテクチャの一貫性
- ❌ data_collector という名前が API サーバーの役割と不一致
- ❌ collector と api が同じパッケージ内に混在

### Option B: 新規パッケージの作成

**戦略:**
- `src/animal_repository/` として完全に独立した新規パッケージを作成
- AnimalData モデルを共有モジュールとして切り出し
- data_collector と animal_repository が独立したサービスとして動作

**具体的な変更:**

1. **新規パッケージ構造:**
   ```
   src/
   ├── data_collector/        # 既存（変更最小限）
   ├── shared/
   │   └── models.py          # AnimalData（共有）
   └── animal_repository/     # 新規
       ├── domain/
       │   └── models.py      # リポジトリ固有のモデル
       ├── infrastructure/
       │   ├── database/
       │   │   ├── connection.py
       │   │   ├── repository.py
       │   │   └── schema.py
       │   └── config.py      # 環境変数管理
       └── api/
           ├── app.py
           ├── routes.py
           └── dependencies.py
   ```

2. **data_collector の修正:**
   - `from shared.models import AnimalData` に変更
   - 新規エンドポイント追加（POST /animals）でデータ挿入

3. **統合ポイント:**
   - data_collector → animal_repository API（HTTP経由でデータ送信）
   - または、data_collector → shared Repository（直接データベースアクセス）

**トレードオフ:**
- ✅ 明確な責任分離（収集 vs 永続化/API提供）
- ✅ 独立したデプロイメントが可能
- ✅ 名前空間の整理
- ❌ ファイル数増加、ナビゲーションが複雑化
- ❌ 共有モジュールの管理が必要
- ❌ 初期構築コストが高い

### Option C: ハイブリッドアプローチ

**戦略:**
- Phase 1: Option A（既存パッケージ内に追加）で MVP 実装
- Phase 2: 必要に応じて Option B（独立パッケージ）にリファクタリング

**具体的なステップ:**

**Phase 1（MVP）:**
1. `src/data_collector/infrastructure/` に database, api モジュールを追加
2. models.py の location を必須化
3. 基本的な CRUD API を実装
4. CollectorService を修正してデータベースに保存

**Phase 2（リファクタリング）:**
1. 必要に応じて animal_repository パッケージを分離
2. マイクロサービス化（data_collector と animal_repository が独立）

**トレードオフ:**
- ✅ 段階的な実装で早期フィードバック
- ✅ 初期コストが低い
- ✅ 将来的な拡張性を維持
- ❌ Phase 2 でのリファクタリングコスト
- ❌ Phase 1 で技術的負債が蓄積する可能性

## 4. 実装複雑度とリスク評価

### 工数見積もり
**サイズ: L（1-2週間）**

**理由:**
- データベーススキーマ設計、マイグレーション作成（2-3日）
- Repository パターン実装、トランザクション管理（2-3日）
- FastAPI エンドポイント実装（2-3日）
- フィルタリング、ページネーション実装（1-2日）
- エラーハンドリング、ロギング統合（1日）
- テスト作成（2-3日）
- 統合テスト、動作確認（1-2日）

### リスクレベル
**リスク: Medium**

**理由:**

**Medium リスク要因:**
- 新規技術導入（FastAPI, SQLAlchemy）が必要だが、成熟したライブラリで豊富なドキュメントあり
- データモデル変更（location 必須化）が既存コードに影響するが、影響範囲は限定的
- Pydantic と SQLAlchemy の統合パターンは確立されている
- データベース選定とマイグレーション戦略は検証が必要

**リスク軽減策:**
- FastAPI + SQLAlchemy + Pydantic の統合パターンをベストプラクティスから採用
- location 必須化の影響範囲を事前調査（KochiAdapter のテスト実行）
- PostgreSQL + Docker による開発環境構築で環境差異を最小化

## 5. 設計フェーズへの推奨事項

### 推奨アプローチ
**Option C（ハイブリッドアプローチ）を推奨**

**Phase 1 で実装すべき範囲:**
1. データベーススキーマ設計（PostgreSQL + SQLAlchemy）
2. AnimalRepository 実装（CRUD + upsert）
3. FastAPI ベースの REST API（7つの要件を満たす）
4. CollectorService との統合（データベース永続化）

**Phase 2 で検討すべき事項:**
- パッケージ分離の必要性
- API 認証・認可の追加
- パフォーマンスチューニング

### 設計フェーズで決定すべき事項

**技術選定:**
1. ✅ **データベース:** PostgreSQL（JSONB、配列型サポート）
2. ✅ **Web フレームワーク:** FastAPI（Pydantic 統合、自動ドキュメント生成）
3. ✅ **ORM:** SQLAlchemy 2.x（async サポート、Pydantic 統合）
4. ⚠️ **マイグレーション:** Alembic（要検証）
5. ⚠️ **設定管理:** pydantic-settings または python-dotenv
6. ⚠️ **ASGI サーバー:** uvicorn（開発・本番両方）

**アーキテクチャ決定:**
1. ディレクトリ構造（Option A ベース）
2. API エンドポイント設計（RESTful 原則）
3. エラーハンドリング戦略（統一的な例外ハンドラー）
4. ロギング統合（既存の logging パターンを拡張）

**データモデル調整:**
1. AnimalData.location の必須化
2. KochiAdapter の location フォールバック実装
3. 既存テストの更新

### 次フェーズで実施すべき調査

**優先度: 高**
1. PostgreSQL スキーマ設計の詳細化（インデックス戦略、パーティショニング検討）
2. SQLAlchemy モデル定義と Pydantic モデルの統合パターン
3. FastAPI のエンドポイント設計（RESTful API ベストプラクティス）

**優先度: 中**
1. Alembic マイグレーション戦略（初期スキーマ、バージョン管理）
2. Docker Compose による開発環境構築
3. API 認証・認可の必要性確認

**優先度: 低**
1. パフォーマンスベンチマーク（想定データ量での負荷テスト）
2. CI/CD パイプライン構築

---

## 追加調査結果（設計フェーズ）

### FastAPI + SQLAlchemy 2.0 + Pydantic 統合パターン

**調査日:** 2026-01-13
**情報源:**
- [FastAPI SQL Databases Tutorial](https://fastapi.tiangolo.com/tutorial/sql-databases/)
- [Setting up FastAPI with Async SQLAlchemy 2.0 & Pydantic V2](https://medium.com/@tclaitken/setting-up-a-fastapi-app-with-async-sqlalchemy-2-0-pydantic-v2-e6c540be4308)
- [FastAPI Dependency Injection with Service and Repository Layers](https://blog.dotcs.me/posts/fastapi-dependency-injection-x-layers)

#### 主要な発見

**1. モデル分離パターン（推奨）**
- **SQLAlchemy Model**: データベーステーブル構造定義（カラム、型、インデックス）
- **Pydantic Schema**: API入出力制御（リクエストバリデーション、レスポンス整形）
- **利点**: 関心の分離、セキュリティ（秘密情報の除外）、保守性

**2. 複数Pydanticモデルパターン**
- `AnimalCreate`: POST リクエスト用（必須フィールドのみ）
- `AnimalPublic`: レスポンス用（source_url含む、内部情報除外）
- `AnimalUpdate`: PATCH リクエスト用（全フィールドオプショナル）
- **実装:** `exclude_unset=True` で部分更新を実現

**3. Async SQLAlchemy 2.0 サポート**
- **接続文字列:** `postgresql+asyncpg://user:pass@host:port/db`
- **ドライバー:** `asyncpg`（PostgreSQL専用高速ドライバー）
- **利点:** 非同期パスオペレーションでのブロッキング解消、スピードアップ

**4. Dependency Injection パターン**
```python
from typing import Annotated
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session

SessionDep = Annotated[AsyncSession, Depends(get_session)]
```
- **利点:** 型安全、再利用可能、テスト可能

**5. Repository パターン統合**
- **構造:** Controller → Service → Repository → Database
- **Repository責務:** データアクセスロジックのカプセル化
- **Service責務:** ビジネスロジック、複数リポジトリの調整

#### PostgreSQL JSONB 配列のベストプラクティス

**情報源:**
- [SQLAlchemy 2.0 PostgreSQL Documentation](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html)
- [JSONB SQLAlchemy Tutorial](https://www.geeksforgeeks.org/python/jsonb-sqlalchemy/)

**主要な発見:**
- **型定義:** `JSONB` 型（SQLAlchemy）でJSONB配列をサポート
- **パフォーマンス:** JSONB はJSONよりインデックス化・検索が高速
- **クエリ:** `func.jsonb_array_elements()` で配列要素の抽出が可能
- **推奨:** 画像URL配列は JSONB 型で格納（検索不要の場合は ARRAY(Text) も選択肢）

### 技術選定の最終決定

| 技術要素 | 選定 | バージョン | 理由 |
|---------|------|-----------|------|
| データベース | PostgreSQL | 14+ | JSONB、配列型、GINインデックスサポート |
| Async Driver | asyncpg | 最新 | 高速、async/await ネイティブサポート |
| ORM | SQLAlchemy | 2.0+ | 非同期サポート、成熟したエコシステム |
| Webフレームワーク | FastAPI | 0.100+ | Pydantic統合、自動APIドキュメント、非同期サポート |
| マイグレーション | Alembic | 1.11+ | SQLAlchemy標準、バージョン管理 |
| 設定管理 | pydantic-settings | 2.0+ | 型安全な環境変数管理 |
| ASGIサーバー | uvicorn | 最新 | 高速、標準的 |

### アーキテクチャ決定

**採用パターン:** レイヤードアーキテクチャ + Repository パターン

**ディレクトリ構造:**
```
src/data_collector/
├── domain/
│   └── models.py              # AnimalData (Pydantic) - 共有
├── infrastructure/
│   ├── database/
│   │   ├── __init__.py
│   │   ├── connection.py      # DB接続、セッション管理
│   │   ├── models.py          # SQLAlchemy ORM モデル
│   │   └── repository.py      # AnimalRepository
│   └── api/
│       ├── __init__.py
│       ├── main.py            # FastAPI アプリケーション
│       ├── routes.py          # エンドポイント定義
│       ├── dependencies.py    # 依存性注入
│       └── schemas.py         # API用Pydanticスキーマ
└── config.py                  # 環境変数設定
```

**統合ポイント:**
1. CollectorService → AnimalRepository（データ挿入）
2. FastAPI routes → AnimalRepository（データ取得）
3. 既存 AnimalData (Pydantic) を両方で共有
4. SQLAlchemy Model は独立定義（`from_attributes=True`でPydantic変換）

## 6. 要件とアセットのマッピング

| 要件 | 既存アセット | ギャップ | 対応方針 |
|------|-------------|---------|---------|
| Req 1: DB スキーマ | AnimalData モデル | ❌ SQLAlchemy モデル、マイグレーション | 新規作成（infrastructure/database/） |
| Req 2: データ永続化 | OutputWriter（JSON） | ❌ Repository、トランザクション管理 | 新規作成（AnimalRepository） |
| Req 3: データ取得API | - | ❌ FastAPI アプリケーション、ルーティング | 新規作成（infrastructure/api/） |
| Req 4: フィルタリング | - | ❌ クエリビルダー | 新規作成（Repository 内） |
| Req 5: ページネーション | - | ❌ offset/limit ロジック | 新規作成（Repository 内） |
| Req 6: エラーハンドリング | logging 使用済み | ⚠️ API エラーハンドラー | 既存パターンを拡張 |
| Req 7: DB 接続管理 | - | ❌ コネクションプール、環境変数管理 | 新規作成（connection.py, config.py） |

**凡例:**
- ✅ 既存アセットで対応可能
- ⚠️ 部分的に対応、拡張が必要
- ❌ 新規実装が必要

