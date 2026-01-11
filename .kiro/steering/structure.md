# Project Structure

## Organization Philosophy

**階層的知識管理**: プロジェクト全体（steering）と個別機能（specs）の分離
**ファイルベース永続化**: Markdown による人間可読な文書、JSON によるメタデータ
**テンプレート駆動**: 一貫性のある構造化、カスタマイズ可能

## Directory Patterns

### Steering（`.kiro/steering/`）
**Purpose**: プロジェクト全体の永続的知識
**Content**: パターン、原則、標準（網羅的リストではない）
**Files**:
- `product.md`: プロダクト概要と価値提案
- `tech.md`: 技術スタックと開発標準
- `structure.md`: プロジェクト構造パターン
- `*.md`: カスタムドメイン知識（例: `api-standards.md`, `testing.md`）

**Update Policy**: 追加的（既存コンテンツを保持）、コードベースとの同期

### Specifications（`.kiro/specs/[feature-name]/`）
**Purpose**: 個別機能の形式化された開発プロセス
**Lifecycle**: 初期化 → 要件 → 設計 → タスク → 実装
**Files**:
- `spec.json`: メタデータ、承認状態、タイムスタンプ
- `requirements.md`: 要件定義（EARS形式推奨）
- `design.md`: 技術設計、アーキテクチャ決定
- `tasks.md`: 実装タスクリスト
- `research.md`: コードベース調査結果（自動生成）

**State Management**: `spec.json` が各フェーズの承認を追跡

### Settings（`.kiro/settings/`）
**Purpose**: フレームワーク設定（メタデータ、ドキュメント対象外）
**Subdirectories**:
- `templates/`: 初期化テンプレート（specs, steering）
- `rules/`: 生成原則とガイドライン

**Note**: これらは steering に文書化しない（設定はプロジェクト知識ではない）

## Naming Conventions

- **Feature Names**: kebab-case（例: `user-authentication`, `shopping-cart`）
- **Steering Files**: kebab-case（例: `api-standards.md`, `testing.md`）
- **Spec Files**: 固定名（`spec.json`, `requirements.md`, `design.md`, `tasks.md`）

## Workflow Patterns

### Bootstrap（新規プロジェクト）
```bash
/kiro:steering              # コードベースから steering 生成
/kiro:spec-init "..."       # 新規仕様初期化
/kiro:spec-requirements     # 要件生成
/kiro:spec-design          # 設計生成
/kiro:spec-tasks           # タスク生成
/kiro:spec-impl            # 実装実行
```

### Sync（既存プロジェクト）
```bash
/kiro:steering              # steering をコードベースと同期
/kiro:spec-status [name]    # 仕様進捗確認
```

## Code Organization Principles

**段階的詳細化**: 各フェーズで適切な粒度（要件は WHAT、設計は HOW、タスクは STEPS）
**承認ゲート**: 各フェーズ完了後に人間レビュー（`-y` フラグで省略可）
**追跡可能性**: 要件 → 設計 → タスク → 実装の明確なリンク
**パターン文書化**: 網羅的リストではなく、判断基準となるパターン

---
_created_at: 2026-01-06_
