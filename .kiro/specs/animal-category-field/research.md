# Research & Design Decisions: animal-category-field

---
**Purpose**: カテゴリフィールド追加に関するディスカバリー結果と設計決定の記録
**Discovery Scope**: Extension（既存システムへのフィールド追加）
---

## Summary

- **Feature**: `animal-category-field`
- **Discovery Scope**: Extension（既存データモデル、API、アダプターへのフィールド追加）
- **Key Findings**:
  1. KochiAdapter は `/jouto/`（譲渡）と `/maigo/`（迷子）の両ページからデータ収集するが、カテゴリ情報を保持していない
  2. `fetch_animal_list()` の返却型変更が必要（URL のみ → URL + カテゴリのタプル）
  3. 既存パターン（field_validator、インデックス、フィルタ）を流用可能

## Research Log

### カテゴリ判定ポイントの特定

- **Context**: 収集元 URL からカテゴリを判定する最適なタイミングの調査
- **Sources Consulted**:
  - `src/data_collector/adapters/kochi_adapter.py` - fetch_animal_list() の実装
  - `src/data_collector/orchestration/collector_service.py` - データフローの確認
- **Findings**:
  - `fetch_animal_list()` は JOUTO_URL と MAIGO_URL それぞれから詳細ページ URL を収集
  - 詳細ページ URL は `/center-data/xxx/` 形式で、元のカテゴリ情報を含まない
  - カテゴリ判定は fetch 時点でのみ可能
- **Implications**: `fetch_animal_list()` の返却型を `List[str]` から `List[Tuple[str, str]]` に変更する必要がある

### 既存バリデーションパターンの調査

- **Context**: category フィールドのバリデーション実装方法
- **Sources Consulted**:
  - `src/data_collector/domain/models.py` - species, sex の field_validator
- **Findings**:
  - Pydantic `@field_validator` デコレータで制約値バリデーション実装済み
  - species: `["犬", "猫", "その他"]`
  - sex: `["男の子", "女の子", "不明"]`
- **Implications**: category も同じパターンで `["adoption", "lost"]` のバリデーターを追加

### データベースインデックス戦略

- **Context**: category カラムのインデックス設計
- **Sources Consulted**:
  - `src/data_collector/infrastructure/database/models.py` - 既存インデックス定義
- **Findings**:
  - 単一カラムインデックス: species, sex, shelter_date, location に `index=True`
  - 複合インデックス: `idx_animals_search` (species, sex, location)
- **Implications**:
  - category に単一インデックス追加
  - 複合インデックスを `(species, sex, location, category)` に拡張

### CollectorService への影響

- **Context**: オーケストレーション層の変更範囲
- **Sources Consulted**:
  - `src/data_collector/orchestration/collector_service.py` - _collect_with_retry()
- **Findings**:
  - 現在: `detail_urls = self.adapter.fetch_animal_list()` → URL リストをループ
  - 変更後: タプルリストを受け取り、category を extract に渡す必要あり
- **Implications**: CollectorService のループ処理を `(url, category)` 展開に変更

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| A: URL パターンマッチング | extract_animal_details で detail_url からカテゴリ推測 | 変更最小 | 詳細 URL にカテゴリ情報なし → 技術的に不可能 | ❌ 不採用 |
| B: タプル返却 | fetch_animal_list() が `List[Tuple[str, str]]` を返却 | 明示的、正確 | インターフェース変更必要 | ✅ 採用 |
| C: 引数追加 | extract_animal_details(url, category) にカテゴリ引数追加 | 責務分離維持 | fetch 側での判定が必要 | B と併用 |

**選択**: オプション B + C の組み合わせ
- fetch_animal_list() がタプルを返却
- extract_animal_details() にカテゴリ引数を追加
- RawAnimalData にカテゴリを含める

## Design Decisions

### Decision: fetch_animal_list() 返却型変更

- **Context**: カテゴリ情報を収集時点で保持する必要がある
- **Alternatives Considered**:
  1. `List[str]` のまま、detail URL からカテゴリを推測 → 不可能
  2. `List[Tuple[str, str]]` に変更 → 採用
  3. 新しい dataclass `AnimalDetailRef(url, category)` を導入 → オーバーエンジニアリング
- **Selected Approach**: `List[Tuple[str, str]]` を返却（url, category のペア）
- **Rationale**:
  - シンプルで明示的
  - 既存コードへの影響を最小化
  - 型ヒントで意図が明確
- **Trade-offs**:
  - MunicipalityAdapter インターフェース変更が必要
  - 将来的に dataclass への移行も可能
- **Follow-up**: 他の自治体アダプター追加時に同じパターンを適用

### Decision: カテゴリ値として英語を使用

- **Context**: カテゴリ値の命名規則
- **Alternatives Considered**:
  1. 日本語: `"譲渡対象"`, `"迷子"` → URL エンコーディング問題
  2. 英語: `"adoption"`, `"lost"` → 採用
- **Selected Approach**: 英語値を使用
- **Rationale**:
  - API パラメータとしての一貫性（他フィールドも英語）
  - URL エンコーディング不要
  - 国際化対応の容易さ
- **Trade-offs**: 日本語表示時にマッピングが必要
- **Follow-up**: フロントエンド（public-web-portal）で表示用ラベルを定義

### Decision: 既存データのデフォルトカテゴリ

- **Context**: マイグレーション時の既存レコード処理
- **Alternatives Considered**:
  1. NULL 許容 → API フィルタが複雑化
  2. デフォルト 'adoption' → 採用
  3. デフォルト 'unknown' → 新しい値の導入が必要
- **Selected Approach**: デフォルト値 `'adoption'` を設定
- **Rationale**:
  - 要件で明示的に指定済み（AC 2.4, 5.1）
  - 現行データの大半は譲渡情報から収集されている想定
  - NOT NULL 制約により一貫性を維持
- **Trade-offs**: 実際には迷子だったデータも 'adoption' になる
- **Follow-up**: 必要に応じて手動で既存データを修正可能

## Risks & Mitigations

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| インターフェース変更による影響範囲 | 中 | 高 | MunicipalityAdapter, CollectorService の同時更新 |
| マイグレーション失敗 | 高 | 低 | rollback スクリプト準備、本番前にステージングで検証 |
| テスト修正漏れ | 中 | 中 | 全テストファイルを事前に洗い出し、CI で検証 |
| 既存 API クライアント影響 | 低 | 低 | category パラメータをオプショナルに |

## References

- Pydantic Field Validators: https://docs.pydantic.dev/latest/concepts/validators/
- Alembic Operations: https://alembic.sqlalchemy.org/en/latest/ops.html
- FastAPI Query Parameters: https://fastapi.tiangolo.com/tutorial/query-params/
