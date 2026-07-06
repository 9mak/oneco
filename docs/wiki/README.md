# oneco Wiki

oneco の体系ドキュメント。各ページはコードを一次ソースとして記述しており、記述と実装が食い違う場合はコードが正です（気づいたらこの Wiki を直してください）。

## 📖 ページ一覧

### 全体像
| ページ | 内容 |
|---|---|
| [アーキテクチャ](01-architecture.md) | 本番構成・コンポーネント一覧・技術スタック |
| [データフロー](02-data-flow.md) | 収集 → 正規化 → DB → API → フロントエンド表示までの流れ |

### バックエンド
| ページ | 内容 |
|---|---|
| [Adapter アーキテクチャ](03-adapters.md) | rule-based adapter の階層・registry・**サイト追加手順** |
| [自己修復ループ](04-self-healing.md) | auto-fix-adapter の3フェーズ（検知 → LLM修復 → 自動マージ） |
| [データベース](05-database.md) | スキーマ・Animal/Archive の関係・pgbouncer 接続の注意点 |
| [REST API](06-api.md) | 公開/内部エンドポイント一覧 |

### フロントエンド・配信
| ページ | 内容 |
|---|---|
| [フロントエンド](07-frontend.md) | Next.js App Router 構成・ISR/SSG 戦略・ページ一覧 |
| [フィード配信と SNS 投稿](08-syndication-sns.md) | RSS/Atom・Threads 自動投稿と安全機構 |

### 運用
| ページ | 内容 |
|---|---|
| [GitHub Actions ワークフロー](09-workflows.md) | 全9ワークフローのトリガー・役割 |
| [監視・アラート体制](10-monitoring.md) | uptime / secret-health / 収集品質監視 / Discord・Slack 通知 |
| [ローカル開発ガイド](11-development.md) | セットアップ・テスト実行・環境変数一覧 |

## 関連ドキュメント（Wiki 外）

- [README](../../README.md) — プロジェクト概要・クイックスタート
- [DEPLOYMENT.md](../../DEPLOYMENT.md) — 本番デプロイ手順
- [docs/RUNBOOK.md](../RUNBOOK.md) — 障害対応ランブック（アラートが鳴ったらここ）
- [CONTRIBUTING.md](../../CONTRIBUTING.md) — 貢献フロー
- `.kiro/steering/` — AI 開発用のプロジェクトコンテキスト
- `.kiro/specs/` — 機能別の仕様（要件・設計・タスク）
