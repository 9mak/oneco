# Gap Analysis: animal-category-field

## 概要

**分析結果**: すべての要件が既にコードベースに実装されています。

本レポートは `animal-category-field` 要件と現行実装のギャップを分析した結果、**実装ギャップなし**という結論に達しました。設計、実装、マイグレーションのすべてが完了しています。

**推奨アクション**: 実装検証フェーズ (`/kiro:validate-impl animal-category-field`) に進み、テストカバレッジと品質を確認してください。

---

## 1. 要件と既存アセットのマッピング

### Requirement 1: ドメインモデルへのカテゴリフィールド追加

| AC# | 受け入れ条件 | 既存アセット | ギャップ |
|-----|-------------|-------------|---------|
| 1.1 | RawAnimalData に category フィールド | `src/data_collector/domain/models.py:32` | ✅ **実装済み** |
| 1.2 | AnimalData に category フィールド ('adoption'/'lost') | `src/data_collector/domain/models.py:48` | ✅ **実装済み** |
| 1.3 | 2値制約バリデーション | `models.py:119-138` validate_category() | ✅ **実装済み** |
| 1.4 | 無効値でバリデーションエラー | Pydantic field_validator パターン | ✅ **実装済み** |
| 1.5 | category を必須フィールドとする | AnimalData.category (必須) | ✅ **実装済み** |

**影響ファイル**: 既に変更済み
- `src/data_collector/domain/models.py`
- `src/data_collector/domain/normalizer.py`

### Requirement 2: データベーススキーマへのカテゴリカラム追加

| AC# | 受け入れ条件 | 既存アセット | ギャップ |
|-----|-------------|-------------|---------|
| 2.1 | Animal テーブルに category カラム | `models.py:43-49` VARCHAR(20), NOT NULL | ✅ **実装済み** |
| 2.2 | category カラムにインデックス | index=True (L48) | ✅ **実装済み** |
| 2.3 | Alembic マイグレーション | `alembic/versions/6134989ff064_*.py` | ✅ **実装済み** |
| 2.4 | 既存データにデフォルト 'adoption' | server_default='adoption' (L47) | ✅ **実装済み** |
| 2.5 | 複合検索インデックスに category 含める | idx_animals_search (L66-68) | ✅ **実装済み** |

**影響ファイル**: 既に変更済み
- `src/data_collector/infrastructure/database/models.py`
- `alembic/versions/6134989ff064_add_category_column_to_animals.py`

### Requirement 3: APIスキーマへのカテゴリフィールド追加

| AC# | 受け入れ条件 | 既存アセット | ギャップ |
|-----|-------------|-------------|---------|
| 3.1 | AnimalPublic に category フィールド | `schemas.py:35` category: str | ✅ **実装済み** |
| 3.2 | GET /animals に category クエリパラメータ | `routes.py:30` Query parameter | ✅ **実装済み** |
| 3.3 | category=adoption でフィルタ | `routes.py:60` repository呼び出し | ✅ **実装済み** |
| 3.4 | category=lost でフィルタ | 同上 | ✅ **実装済み** |
| 3.5 | category 省略で全件 | Optional[str] = None (L30) | ✅ **実装済み** |
| 3.6 | 無効カテゴリで HTTP 400 | `routes.py:42-46` バリデーション | ✅ **実装済み** |

**影響ファイル**: 既に変更済み
- `src/data_collector/infrastructure/api/schemas.py`
- `src/data_collector/infrastructure/api/routes.py`
- `src/data_collector/infrastructure/database/repository.py`

### Requirement 4: アダプターでのカテゴリ判定

| AC# | 受け入れ条件 | 既存アセット | ギャップ |
|-----|-------------|-------------|---------|
| 4.1 | /jouto/ から収集時に 'adoption' 設定 | `kochi_adapter.py:77-79` 実装済み | ✅ **実装済み** |
| 4.2 | /maigo/ から収集時に 'lost' 設定 | `kochi_adapter.py:77-79` 実装済み | ✅ **実装済み** |
| 4.3 | MunicipalityAdapter インターフェース拡張 | `municipality_adapter.py:85,100-102` | ✅ **実装済み** |
| 4.4 | 新規アダプターでの同様実装 | インターフェース定義済み | ✅ **ガイド済み** |
| 4.5 | 判定不可時のデフォルト + 警告 | `kochi_adapter.py:153` デフォルト値 | ✅ **実装済み** |

**実装確認**:
- `fetch_animal_list()` は `List[Tuple[str, str]]` を返却 (URL, category)
- 譲渡情報と迷子情報の両方から収集し、カテゴリを保持
- `extract_animal_details()` は category パラメータを受け取る
- CollectorService も対応済み (L224-244)

**影響ファイル**: 既に変更済み
- `src/data_collector/adapters/kochi_adapter.py`
- `src/data_collector/adapters/municipality_adapter.py`
- `src/data_collector/orchestration/collector_service.py`

### Requirement 5: 既存データとの後方互換性

| AC# | 受け入れ条件 | 既存アセット | ギャップ |
|-----|-------------|-------------|---------|
| 5.1 | 既存レコードにデフォルト 'adoption' | migration file L30 server_default | ✅ **実装済み** |
| 5.2 | category なしリクエスト受付 | `routes.py:30` Optional[str] = None | ✅ **実装済み** |
| 5.3 | 既存クライアント動作保証 | オプショナルパラメータ設計 | ✅ **実装済み** |
| 5.4 | ロールバック可能マイグレーション | migration file L48-64 downgrade() | ✅ **実装済み** |
| 5.5 | source_url 一意性維持 | `models.py:39` unique=True | ✅ **維持済み** |

---

## 2. 実装状況サマリー

### ✅ すべての要件が実装済み

すべての受け入れ条件が既にコードベースに実装されています:

1. **ドメインモデル**: RawAnimalData, AnimalData に category フィールド追加、バリデーション実装
2. **データベース**: Animal テーブルに category カラム追加、インデックス作成、マイグレーション作成
3. **API**: AnimalPublic スキーマ、クエリパラメータ、フィルタリング、バリデーション実装
4. **アダプター**: KochiAdapter でカテゴリ判定、MunicipalityAdapter インターフェース更新
5. **後方互換性**: デフォルト値、オプショナルパラメータ、ロールバック機能実装

### 実装済みファイル一覧

| ファイル | 変更内容 | 状態 |
|---------|---------|------|
| `domain/models.py` | category フィールド追加、バリデーション | ✅ 完了 |
| `domain/normalizer.py` | category フィールド受け渡し | ✅ 完了 |
| `infrastructure/database/models.py` | category カラム追加、インデックス | ✅ 完了 |
| `infrastructure/database/repository.py` | category フィルタ、変換 | ✅ 完了 |
| `infrastructure/api/schemas.py` | category フィールド追加 | ✅ 完了 |
| `infrastructure/api/routes.py` | category パラメータ、バリデーション | ✅ 完了 |
| `adapters/municipality_adapter.py` | インターフェース更新 | ✅ 完了 |
| `adapters/kochi_adapter.py` | カテゴリ判定ロジック | ✅ 完了 |
| `orchestration/collector_service.py` | カテゴリ対応 | ✅ 完了 |
| `alembic/versions/6134989ff064_*.py` | マイグレーション | ✅ 完了 |

---

## 3. 実装オプション分析 (過去の検討)

### オプション A: 最小限変更（URL パターンマッチング）

**概要**: `extract_animal_details()` の detail_url からカテゴリを推測

**メリット**:
- 変更量最小
- 既存メソッドシグネチャを変更せずに済む

**デメリット**:
- 推測が不正確になる可能性（detail URL にカテゴリ情報がない場合）
- 高知県サイトでは `/center-data/` という統一パスを使用しており、元のページ（/jouto/ or /maigo/）の情報は detail URL からは判別不可

**推奨度**: ❌ 不可 - 技術的に実現不可能

### オプション B: URL とカテゴリのペア返却（推奨）

**概要**: `fetch_animal_list()` が URL とカテゴリのタプルリストを返却

```python
def fetch_animal_list(self) -> List[Tuple[str, str]]:
    """Returns: List[(detail_url, category)]"""
```

**メリット**:
- カテゴリ情報を収集時点で正確に保持
- 明示的なデータフロー
- 将来の拡張に対応しやすい

**デメリット**:
- MunicipalityAdapter インターフェース変更
- 呼び出し側（CollectorService）の変更が必要

**推奨度**: ✅ 推奨

### オプション C: RawAnimalData にカテゴリを含めて extract で設定

**概要**: `extract_animal_details()` にカテゴリを引数として渡す

```python
def extract_animal_details(self, detail_url: str, category: str) -> RawAnimalData:
```

**メリット**:
- fetch と extract の責務分離を維持
- RawAnimalData の自然な拡張

**デメリット**:
- インターフェース変更が必要

**推奨度**: ✅ 許容可能（オプション B の代替）

---

## 3. データフロー影響分析

### 現行データフロー

```
KochiAdapter.fetch_animal_list()
    ↓ List[str] (URLs only)
KochiAdapter.extract_animal_details(url)
    ↓ RawAnimalData (no category)
KochiAdapter.normalize(raw_data)
    ↓ AnimalData (no category)
AnimalRepository.save_animal(animal_data)
    ↓ Animal ORM (no category)
GET /animals
    ↓ AnimalPublic (no category)
```

### 提案データフロー（オプション B）

```
KochiAdapter.fetch_animal_list()
    ↓ List[Tuple[str, str]] (URLs + categories)
KochiAdapter.extract_animal_details(url, category)
    ↓ RawAnimalData (with category)
KochiAdapter.normalize(raw_data)
    ↓ AnimalData (with category validation)
AnimalRepository.save_animal(animal_data)
    ↓ Animal ORM (with category column)
GET /animals?category=adoption
    ↓ AnimalPublic (with category field)
```

---

## 4. 変更対象ファイル一覧

| ファイル | 変更種別 | 優先度 | 推定影響度 |
|---------|---------|--------|-----------|
| `domain/models.py` | 修正 | 高 | 中 |
| `domain/normalizer.py` | 修正 | 高 | 低 |
| `infrastructure/database/models.py` | 修正 | 高 | 中 |
| `infrastructure/database/repository.py` | 修正 | 高 | 中 |
| `infrastructure/api/schemas.py` | 修正 | 高 | 低 |
| `infrastructure/api/routes.py` | 修正 | 高 | 中 |
| `adapters/municipality_adapter.py` | 修正 | 高 | 低 |
| `adapters/kochi_adapter.py` | 修正 | 高 | 高 |
| `alembic/versions/` | 新規 | 高 | 低 |
| `tests/domain/test_models.py` | 修正 | 中 | 中 |
| `tests/domain/test_normalizer.py` | 修正 | 中 | 低 |
| `tests/adapters/test_kochi_adapter.py` | 修正 | 中 | 高 |
| `tests/` (API, Repository) | 修正 | 中 | 中 |

---

## 5. リスク評価

### 高リスク

| リスク | 影響 | 緩和策 |
|-------|------|--------|
| 既存データのカテゴリ不明 | 全既存レコードが 'adoption' になる | 要件で許容済み（デフォルト 'adoption'） |
| テスト修正漏れ | CI 失敗 | 全テストファイルを事前に洗い出し |

### 中リスク

| リスク | 影響 | 緩和策 |
|-------|------|--------|
| インターフェース変更による影響 | CollectorService の修正必要 | 設計フェーズで明確化 |
| マイグレーション失敗 | 本番デプロイ時の問題 | ロールバックスクリプト準備 |

### 低リスク

| リスク | 影響 | 緩和策 |
|-------|------|--------|
| API 後方互換性 | 既存クライアント影響 | category をオプショナルに |

---

## 6. 推奨事項

### 設計フェーズへの推奨

1. **オプション B（URL + カテゴリのペア返却）を採用**
   - 明示的なデータフローで保守性が高い
   - カテゴリ情報の正確性を保証

2. **変更順序の推奨**
   1. ドメインモデル（RawAnimalData, AnimalData）
   2. データベースモデル + マイグレーション
   3. アダプター（KochiAdapter）
   4. リポジトリ（AnimalRepository）
   5. API（スキーマ、ルート）
   6. テスト更新

3. **テスト戦略**
   - 各レイヤーで単体テスト追加
   - 統合テストでエンドツーエンド確認
   - マイグレーションの rollback テスト

4. **マイグレーション戦略**
   - `category` カラムを `VARCHAR(20) NOT NULL DEFAULT 'adoption'` で追加
   - 既存レコードは自動的に 'adoption' になる
   - downgrade でカラム削除

---

## 7. 結論

**実装ギャップ: なし**

すべての要件が既にコードベースに実装されています。設計、実装、マイグレーションのすべてが完了しており、新規開発は不要です。

### 実装された主要な変更

1. **オプション B（URL + カテゴリのペア返却）を採用済み**
   - `fetch_animal_list()` が `List[Tuple[str, str]]` を返却
   - 明示的なデータフローで保守性が高い実装

2. **全レイヤーでカテゴリ対応完了**
   - ドメインモデル（バリデーション含む）
   - データベースモデル（マイグレーション含む）
   - アダプター（カテゴリ判定ロジック）
   - リポジトリ（フィルタリング）
   - API（スキーマ、ルート、バリデーション）

3. **後方互換性の確保**
   - 既存データへのデフォルト値設定
   - オプショナルなクエリパラメータ
   - ロールバック可能なマイグレーション

### 次のステップ

**推奨**: 実装検証フェーズに進む

```bash
/kiro:validate-impl animal-category-field
```

**検証項目**:
1. ✓ すべての要件が実装されているか
2. ✓ テストカバレッジは十分か
3. ✓ エッジケースが考慮されているか
4. ✓ エラーハンドリングは適切か
5. ✓ ドキュメントは更新されているか
6. ✓ パフォーマンスへの影響は許容範囲か

**代替**: 設計レビューを実施したい場合

既存の `design.md` を確認し、必要に応じて設計検証を実施:

```bash
/kiro:validate-design animal-category-field
```

---

## 付録: 過去の検討内容

以下のセクションは、この機能の設計時に検討された内容です。最終的に **オプション B** が採用され、実装されています。
