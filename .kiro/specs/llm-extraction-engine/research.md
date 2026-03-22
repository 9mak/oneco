# Research & Design Decisions

## Summary
- **Feature**: `llm-extraction-engine`
- **Discovery Scope**: Complex Integration（新規AI抽出エンジン + 既存パイプラインとの統合）
- **Key Findings**:
  - Anthropic tool_use + `strict: true` で RawAnimalData スキーマに完全準拠した構造化出力が可能
  - 既存 MunicipalityAdapter インターフェースを実装することで、パイプライン下流（normalizer/repository）は変更不要
  - HTML前処理でトークン数を70-80%削減可能（script/style/nav除去）

## Research Log

### Anthropic Structured Output API
- **Context**: LLM抽出の型安全性確保のため、構造化出力の仕組みを調査
- **Sources**: Anthropic公式ドキュメント（tool_use, structured-outputs）
- **Findings**:
  - `tools` パラメータに JSON Schema を定義し、`tool_choice: {"type": "tool", "name": "extract_animal"}` で強制呼び出し
  - `strict: true` オプションでスキーマ完全準拠を保証（型不一致・フィールド欠損を排除）
  - レスポンスの `content[].type == "tool_use"` ブロックから `input` フィールドで構造化データ取得
  - Python SDK: `anthropic.Anthropic().messages.create()` で利用
- **Implications**: RawAnimalData の全フィールドを JSON Schema として定義し、tool_use で抽出すれば型安全性を担保できる

### OpenAI / Google 構造化出力
- **Context**: プロバイダー差し替え対応のため、各社の構造化出力APIを調査
- **Findings**:
  - OpenAI: `response_format: {"type": "json_schema", "json_schema": {...}}` で JSON Mode、または Function Calling
  - Google Gemini: `generation_config.response_mime_type = "application/json"` + `response_schema` で構造化出力
  - 全プロバイダーで JSON Schema ベースの構造化出力が可能 → 統一インターフェースは実現可能
- **Implications**: 共通インターフェースは「プロンプト + JSON Schema → 構造化データ」で統一できる

### 既存アーキテクチャ分析
- **Context**: 既存パイプラインとの統合方式を決定するため
- **Findings**:
  - `MunicipalityAdapter`（ABC）: `fetch_animal_list()`, `extract_animal_details()`, `normalize()` の3メソッド
  - `CollectorService`: adapter を受け取り `run_collection()` で一括処理
  - `__main__.py`: `KochiAdapter()` をハードコード → 設定ベースのアダプター選択が必要
  - `DataNormalizer`: 静的メソッドで RawAnimalData → AnimalData 変換（共通利用可能）
  - `SnapshotStore`: JSON ファイルベースの差分検知（source_url で比較可能）
- **Implications**: `LlmAdapter` が `MunicipalityAdapter` を継承すれば、CollectorService 以下は変更不要

### HTML前処理によるトークン削減
- **Context**: APIコスト最適化のため
- **Findings**:
  - 典型的な自治体サイトの詳細ページ: 全体HTML 20,000-50,000トークン
  - script/style/nav/footer/header除去後: 3,000-8,000トークン（70-85%削減）
  - BeautifulSoup の `decompose()` で不要要素を除去し、`get_text()` または最小HTML化が有効
  - 画像URL抽出が必要なため、img タグは保持する必要あり
- **Implications**: HTML前処理層を挟むことでコストを大幅削減。Haiku で 1ページあたり約$0.001以下

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Strategy Pattern | LlmProvider インターフェースで各プロバイダーを差し替え | シンプル、テスト容易 | プロバイダー固有の機能が使いにくい | 採用 |
| Plugin System | 動的ロードでプロバイダーを追加 | 拡張性高い | 初期段階では過剰 | 将来検討 |
| Adapter + Strategy | MunicipalityAdapter継承 + LlmProvider差し替え | 既存パイプライン互換 + 柔軟性 | 2層の抽象化 | 採用（組み合わせ） |

## Design Decisions

### Decision: LlmAdapter は MunicipalityAdapter を継承する
- **Context**: 既存の CollectorService パイプラインとの互換性確保
- **Alternatives Considered**:
  1. 完全に新しいパイプラインを構築 — CollectorService も書き直し
  2. MunicipalityAdapter を継承 — 既存パイプラインをそのまま利用
- **Selected Approach**: Option 2（MunicipalityAdapter 継承）
- **Rationale**: DB/API/フロントエンドを一切変更せずに動作させる要件（Req 4）に合致
- **Trade-offs**: LlmAdapter が MunicipalityAdapter の全メソッドを実装する必要がある

### Decision: YAML設定 + Pydantic バリデーション
- **Context**: サイト定義の型安全な読み込み（Req 1）
- **Selected Approach**: PyYAML で読み込み → Pydantic モデルでバリデーション
- **Rationale**: 既にプロジェクトで Pydantic を使用しており、一貫性がある

### Decision: tool_use による構造化抽出
- **Context**: 型安全な抽出結果の取得（Req 3, 8）
- **Selected Approach**: 各プロバイダーの構造化出力APIを使用（Anthropic: tool_use, OpenAI: json_schema, Google: response_schema）
- **Rationale**: プロバイダーごとに最適な構造化出力APIを使い、共通インターフェースで統一

## Risks & Mitigations
- **LLM抽出精度**: 特定のサイト構造で精度が低い可能性 → バリデーション層 + ログで監視、精度が低いサイトはモデルアップグレードまたはルールベースにフォールバック
- **APIコスト超過**: 想定以上のトークン消費 → HTML前処理 + Haiku デフォルト + max_pages 制限
- **サイト構造変更**: 一覧ページのリンクパターンが変わる → LLMベースのリンク推定をフォールバックとして用意
- **レート制限**: 短時間に大量API呼び出し → リクエスト間隔1秒 + 指数バックオフ

## References
- [Anthropic Tool Use](https://docs.anthropic.com/en/docs/build-with-claude/tool-use) — 構造化出力API
- [Anthropic Structured Outputs](https://docs.anthropic.com/en/docs/build-with-claude/structured-outputs) — strict mode
- [OpenAI JSON Mode](https://platform.openai.com/docs/guides/structured-outputs) — OpenAI 構造化出力
- [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/bs4/doc/) — HTML前処理
