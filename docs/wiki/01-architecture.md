# アーキテクチャ

## 全体図

```
自治体・保護団体サイト (211サイト / 47都道府県)
     │  rule-based スクレイピング（LLM は adapter 修復専用）
     ▼
GitHub Actions (data-collector.yml, 毎日 JST 0:00)
     │  正規化・PII伏字・差分検知
     ▼
Supabase PostgreSQL ←──── alembic マイグレーション
     │  (pgbouncer transaction-mode プーラー :6543)
     ▼
Google Cloud Run (FastAPI backend, asia-northeast1)
     │  REST API + /feeds (RSS/Atom)
     ▼
Vercel (Next.js frontend)  ── ISR/SSG で配信
```

## 本番環境

| コンポーネント | サービス | 備考 |
|---|---|---|
| Backend API | Google Cloud Run `oneco-api` (asia-northeast1) | `deploy-backend.yml` で WIF キーレスデプロイ |
| Frontend | Vercel | `main` push で自動デプロイ |
| Database | Supabase PostgreSQL (aws-1-ap-northeast-2) | transaction-mode プーラー経由 (PR #233) |
| Data Collector | GitHub Actions | 毎日 JST 0:00 自動実行 |
| SNS 投稿 | GitHub Actions | 毎日 JST 9:00 (Threads) |

## コンポーネント（`src/` 3パッケージ）

### `src/data_collector/` — 収集・正規化・保存・公開 API の中核

| サブモジュール | 責務 |
|---|---|
| `adapters/` | サイト別スクレイピング。抽象基底 `MunicipalityAdapter`、rule-based フレームワーク + サイト個別 adapter 93ファイル → [Adapter アーキテクチャ](03-adapters.md) |
| `domain/` | `models.py` (RawAnimalData/AnimalData)、`normalizer.py` (正規化・PII伏字)、`diff_detector.py`、`quality_metrics.py` |
| `infrastructure/` | `database/` (SQLAlchemy)、`api/` (FastAPI)、`output_writer.py`、`snapshot_store.py`、`notification_client.py`、`secret_health.py` |
| `orchestration/` | `collector_service.py` (1サイト収集の実行本体)、`parallel_runner.py` (ドメイン単位並列)、`soft_deadline.py` |
| `llm/` | Groq プロバイダー・fetcher・robots checker。**抽出のフォールバック用**（デフォルトは rule-based） |
| `services/` | `archive_service.py` (180日で archive へ移動)、`scheduler.py` |
| `config/sites.yaml` | 全サイト定義（211エントリ、`default_extraction: rule-based`） |

- CLI: `python -m data_collector`（`__main__.py`）
- API サーバー: `uvicorn run_server:app` → `infrastructure/api/app.py` の `create_app()`

### `src/syndication_service/` — フィード配信 + SNS 自動投稿

- RSS/Atom フィード生成（`services/feed_generator.py`）。FastAPI に `/feeds` prefix でマウント（`app.py`）
- Threads 自動投稿（`sns_publisher/`）→ [フィード配信と SNS 投稿](08-syndication-sns.md)

### `src/notification_manager/` — LINE 通知（**未配線・将来機能**)

希望条件（species/sex/size）マッチで LINE 通知する設計。LINE ユーザー ID は暗号化保存（`domain/encryption.py`）。実装済みだが本番未配線。現在の運用アラートは Slack/Discord（→ [監視](10-monitoring.md)）。

## 技術スタック

| レイヤー | 技術 |
|---|---|
| Backend | Python 3.11 / FastAPI / SQLAlchemy (async) + asyncpg / alembic / pdfplumber / Playwright (JS必須27サイト) |
| Frontend | Next.js 16 App Router / React 19 / Tailwind CSS v4 / Auth.js v5 / d3-geo (日本地図) |
| LLM | Groq `llama-3.3-70b-versatile`（adapter 自己修復専用。Anthropic は不採用） |
| CI/CD | GitHub Actions（9ワークフロー → [一覧](09-workflows.md)）/ ruff / pytest / Vitest / Playwright E2E |
| インフラ | Cloud Run + Artifact Registry (WIF) / Vercel / Supabase |
