# Research & Design Decisions

## Summary
- **Feature**: `rule-based-extraction-engine`
- **Discovery Scope**: Extension（既存 data_collector への抽出方式追加）
- **Key Findings**:
  - 既存 `MunicipalityAdapter` (ABC) インターフェース (`fetch_animal_list` / `extract_animal_details` / `normalize`) を継承する形で各種 rule-based 基底クラスを実装可能
  - 既存 `LlmAdapter` (`llm/adapter.py`) も同インターフェース準拠 → 並列共存で問題なし
  - 既存 `__main__.py` の `PROVIDER_REGISTRY` + `create_provider` + `run_llm_sites` 構造を踏襲し `run_rule_based_sites` を追加するだけでよい
  - 92 ユニークテンプレートのうち、種別ごとの分布: standard(list+detail) 44 / single_page 129 / requires_js 25 / pdf 11

## Research Log

### 既存アダプターインターフェースの調査
- **Context**: rule-based 実装が既存 LLM 抽出と無干渉に共存できるか
- **Sources Consulted**: `src/data_collector/adapters/municipality_adapter.py`, `src/data_collector/llm/adapter.py`, `src/data_collector/__main__.py`
- **Findings**:
  - `MunicipalityAdapter` は ABC で 3 つの抽象メソッドを要求 (`fetch_animal_list`, `extract_animal_details`, `normalize`)
  - `KochiAdapter` (798 行) と `LlmAdapter` の両方が既に同インターフェースを実装
  - `CollectorService` (`orchestration/collector_service.py`) は `MunicipalityAdapter` 型を受け取り、抽象に依存（具象を意識しない）
  - `__main__.py` には `run_llm_sites()` 関数があり、サイトの `extraction` 値で振り分け可能
- **Implications**:
  - 既存インターフェースを変更せず派生クラスを追加するだけで rule-based 実装を組み込める
  - サイト個別 adapter（例: `KumamotoAdapter`、`SagaPrefAdapter`）は基底クラスから派生する形で書ける
  - `CollectorService` 側の修正は不要

### テンプレート集約解析
- **Context**: 209 サイトを何個の adapter で対応可能か
- **Sources Consulted**: `scripts/template_analysis_2026-05-15.md`, `src/data_collector/config/sites.yaml`
- **Findings**:
  - 92 ユニーク signature (domain × single_page × requires_js × pdf 等のフラグ組合せ)
  - Top 10 で 31% / Top 30 で 62% / Top 50 で 80% / Top 80 で 94% カバー
  - 1 サイトのみのテンプレートが 45 個（長尾、工数の半分）
  - 同一ドメイン複数サイト（例: `pref.fukushima.lg.jp` 6サイト）は同テンプレで吸収可能
- **Implications**:
  - 1 adapter = 1 ドメイン + フラグ組合せが基本単位
  - 派生クラスは「サイト別 selector 定数」だけを持てばよい構造が望ましい
  - 長尾 45 サイトは shared base から最小コードで派生させる必要

### 既存の補助モジュールの再利用性
- **Context**: HTTP fetch / HTML パース / Playwright / PDF 解析の既存実装を rule-based でも使えるか
- **Sources Consulted**: `src/data_collector/llm/fetcher.py`, `src/data_collector/llm/html_preprocessor.py`
- **Findings**:
  - `PageFetcher` は LLM/rule 関係なく汎用的に使える HTTP/Playwright fetcher
  - `HtmlPreprocessor` は LLM 用クリーニング目的のため、rule-based では使わない
  - PDF 取得処理は `LlmAdapter` 内に散在 → 切り出して共通化推奨
- **Implications**:
  - `PageFetcher` を `llm/` から `adapters/base/` または共通 `infrastructure/` に移動するか、現位置のまま参照する
  - rule-based では生 HTML を直接 BeautifulSoup に渡す（クリーニング不要）

### TDD 戦略：HTML スナップショットテスト
- **Context**: 92 個の adapter の動作保証をどう実現するか
- **Sources Consulted**: `tests/adapters/test_kochi_adapter.py`, `tests/llm/test_adapter.py`
- **Findings**:
  - 既存 `test_kochi_adapter.py` は実 HTML を fixture として使用（HTTP モック）
  - HTTP モック + 期待 RawAnimalData の比較が標準パターン
  - 178 件の既存テストが pass している実績あり
- **Implications**:
  - 各 adapter ごとに `tests/adapters/fixtures/{site_slug}/list.html` + `detail_*.html` + `expected.json` を用意
  - HTTP/HTTPS リクエストは `responses` または `pytest-mock` でスタブ
  - HTML サンプルは「実サイトから 1 回取得 → コミット」で固定化

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| **Template Method** (採用) | 基底クラスがアルゴリズム骨格を持ち、サイト固有部分を派生で hook | 共通処理の重複削減、テスト容易、新規追加最小コード | 基底変更が全派生に影響 | KochiAdapter のパターンと整合 |
| Strategy Pattern | 抽出戦略を独立クラスとして注入 | 切替柔軟 | 余計な間接化、現状の構造から乖離 | 不採用 |
| Pure Functions + Config | 関数 + サイト config dict で済ませる | 最小コード | 型安全性低、Polymorphism 失う、共通処理散在 | 不採用 |

## Design Decisions

### Decision: 基底クラス階層の構造
- **Context**: 92 テンプレートを 4 種類の基底クラスで吸収する具体構造
- **Alternatives Considered**:
  1. 4 つの並列基底クラス（独立）
  2. 共通親 `RuleBasedAdapter` を最上位に置き、4 つを派生
- **Selected Approach**: **(2) 共通親 + 4 派生クラス**
  - `RuleBasedAdapter(MunicipalityAdapter)`: 共通の HTTP/正規化ヘルパー
  - `WordPressListAdapter(RuleBasedAdapter)`: WordPress 系 list+detail
  - `SinglePageTableAdapter(RuleBasedAdapter)`: テーブル/カード一覧で詳細ページなし
  - `PlaywrightAdapter(RuleBasedAdapter)`: JS必須サイト
  - `PdfTableAdapter(RuleBasedAdapter)`: PDF 抽出
- **Rationale**: 共通処理（normalize、image_url 絶対化、phone 正規化等）を一箇所に集約できる
- **Trade-offs**: 階層が 1 段深くなるが、92 個の adapter 実装の総コードは大幅減
- **Follow-up**: 共通親に置くべき機能の取捨選択を Phase A2 序盤で確定

### Decision: 既存 LLM プロバイダの位置づけ
- **Context**: 完全 rule-based 化後の LLM コードの扱い
- **Alternatives Considered**:
  1. LLM プロバイダを完全削除（クリーン）
  2. LLM プロバイダを残しつつ default を rule-based に
- **Selected Approach**: **(2) 残す**
  - 削除しない、コード/テスト保持
  - `default_provider: rule-based` を sites.yaml で指定
  - per-site `extraction: llm` で個別 fallback 可能
- **Rationale**: 収益化後の復帰コストをゼロに、rule破損時の救済策、新規サイト追加の試験用途
- **Trade-offs**: 死コード扱いになる期間が発生するが、コード量は容認範囲
- **Follow-up**: 1 年後に使われていないなら削除を再検討

### Decision: マイグレーションの順序
- **Context**: 92 テンプレートをどの順で実装するか
- **Alternatives Considered**:
  1. 高ボリューム順 (Top カバレッジ優先)
  2. 種別ごと一括 (single_page 全部 → 次 standard)
  3. 簡単な順 (single_page → standard → requires_js → pdf)
- **Selected Approach**: **ハイブリッド**
  - Phase A2 で基底クラスを各種別 1 つずつ完成（4 種）
  - Phase A3a: 各種別 Top 5 = 20 サイト分実装してパターン確立
  - Phase A3b: 残りを高ボリューム順に消化
- **Rationale**: 早期に「全種別動く」状態を作る + 重要サイトを優先
- **Trade-offs**: 完全カバレッジ重視ではないが、リスク分散になる

### Decision: テストフィクスチャの保管方針
- **Context**: HTML スナップショットをどこに置くか
- **Alternatives Considered**:
  1. リポジトリにコミット (容量増)
  2. 別 repo / S3 等に分離
  3. 動的取得 (CI 時に fetch)
- **Selected Approach**: **(1) リポジトリにコミット**
  - `tests/adapters/fixtures/{site_slug}/list.html` 等
  - 1 サイトあたり 50-200KB を許容
- **Rationale**: テスト独立性、CI高速化、外部依存ゼロ
- **Trade-offs**: 92 サイト × 平均 100KB = 約 10MB のリポジトリサイズ増 → 容認範囲
- **Follow-up**: フィクスチャ更新時のワークフロー（手動 fetch スクリプト）を整備

## Risks & Mitigations
- **Risk**: HTML drift で 90 サイト動作後に 1 サイト壊れる → **Mitigation**: per-site Slack 通知 + LLM fallback 切替で救済
- **Risk**: 92 アダプター実装の中で似たコードが繰り返される（DRY 違反） → **Mitigation**: Phase A3 中盤でリファクタリングのチェックポイントを設置
- **Risk**: 長尾 45 個の 1サイトテンプレートで実装意欲が下がる → **Mitigation**: 進捗トラッカー（実装済み数 / 92）を CLI で表示

## References
- [scripts/template_analysis_2026-05-15.md](../../../scripts/template_analysis_2026-05-15.md) — 209 サイトのテンプレート集約解析結果
- [.kiro/specs/llm-extraction-engine/requirements.md](../llm-extraction-engine/requirements.md) — 既存 LLM 抽出エンジンの要件 (前身)
- [.kiro/specs/data-collector/design.md](../data-collector/design.md) — Adapter 層の既存設計
- [src/data_collector/adapters/municipality_adapter.py](../../../src/data_collector/adapters/municipality_adapter.py) — 基底 ABC の現状定義
- [src/data_collector/adapters/kochi_adapter.py](../../../src/data_collector/adapters/kochi_adapter.py) — 参照実装（798 行）
