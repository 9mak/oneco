# Technology Stack

## Architecture

メタフレームワーク: AI 開発ライフサイクル管理
- Claude Code スキル/コマンドシステムとの統合
- ファイルベースの知識管理（Markdown + JSON）
- ステートフルな仕様追跡

## Core Technologies

- **Platform**: Claude Code CLI
- **Storage**: File-based (Markdown for docs, JSON for metadata)
- **Language**: 日本語 (output), English (internal processing)

## Key Components

### `.kiro/steering/`
プロジェクト全体の永続的知識
- `product.md`: プロダクト目的と価値
- `tech.md`: 技術スタックと標準
- `structure.md`: プロジェクト構造パターン
- カスタムファイル: 専門ドメイン知識（API、テスト、セキュリティなど）

### `.kiro/specs/`
個別機能の形式化された開発プロセス
- `spec.json`: メタデータと承認状態
- `requirements.md`: 要件定義
- `design.md`: 技術設計
- `tasks.md`: 実装タスク
- `research.md`: コードベース調査結果

### `.kiro/settings/`
フレームワーク設定（ユーザー文書化対象外）
- `templates/`: 初期化テンプレート
- `rules/`: 生成ルールと原則

## Development Standards

### Phase Separation
- 各フェーズは独立して承認
- `-y` フラグなしでは人間レビュー必須
- 段階的な詳細化（要件 → 設計 → タスク）

### Output Language
- AI内部処理: 英語（思考）
- 生成ファイル: 日本語（`spec.json.language` に従う）
- コミュニケーション: 日本語

### Documentation Granularity
- パターンを文書化、網羅的リストは避ける
- "Golden Rule": 既存パターンに従う新コードは steering 更新不要
- 具体例で原則を示す

## Key Technical Decisions

**ファイルベースストレージ**: データベース不要、Git で追跡可能、人間が読める
**段階的承認**: スコープクリープ防止、各段階での明確なチェックポイント
**テンプレート駆動**: 一貫性確保、カスタマイズ可能
**JIT コードベース分析**: 必要時のみ読み込み、効率的な文脈管理

---
_created_at: 2026-01-06_
