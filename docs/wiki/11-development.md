# ローカル開発ガイド

## セットアップ

```bash
git clone https://github.com/9mak/oneco.git && cd oneco

# Python 3.11 で venv を作成（CI と同じバージョン）
python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"

# 環境変数
cp .env.example .env          # バックエンド
cd frontend && cp .env.local.example .env.local && cd ..

# DB（docker-compose で Postgres を立てる場合）
docker compose up -d
alembic upgrade head

# API サーバー (:8000)
uvicorn run_server:app --reload

# フロントエンド (:3000)
cd frontend && npm install && npm run dev
```

## テスト

```bash
# バックエンド（.venv の Python = 3.11 を使うこと。CI と一致）
.venv/bin/python -m pytest

# adapter / registry テストは PYTHONPATH=src が必要
PYTHONPATH=src .venv/bin/python -m pytest tests/adapters/

# カバレッジ
.venv/bin/python -m pytest --cov=src --cov-report=html

# フロントエンド
cd frontend
npm test           # Vitest
npm run test:e2e   # Playwright
npm run test:a11y  # アクセシビリティ
```

## Lint（コミット前に必ず）

```bash
python3 -m ruff check src/ tests/
python3 -m ruff format src/ tests/   # CI は format --check も通す。個別ファイルだけでなく全体で確認
```

※ mypy は既知エラー約 120 件のため CI ゲート無効（`|| true`）。

## 収集の手動実行

```bash
PYTHONPATH=src .venv/bin/python -m data_collector              # 全サイト
PYTHONPATH=src .venv/bin/python -m data_collector --kochi-only # 高知のみ
```

## 主要な環境変数

### バックエンド / API

| 変数 | 説明 |
|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://...`。本番は Supabase transaction-mode プーラー（:6543） |
| `CORS_ORIGINS` | 許可オリジン |
| `LOG_LEVEL` | INFO / DEBUG |
| `INTERNAL_API_TOKEN` | 内部 API（ステータス更新）の認証トークン |

### Data Collector

| 変数 | 既定 | 説明 |
|---|---|---|
| `GROQ_API_KEY` | — | adapter 自己修復用（抽出は rule-based なので通常収集には不要） |
| `SITE_TIMEOUT_SEC` / `SITE_TIMEOUT_JS_SEC` | 120 / 180 | サイト毎タイムアウト |
| `ONECO_COLLECT_MAX_WORKERS` | — | 並列度（ドメイン単位） |
| `BROKEN_SITE_SKIP_THRESHOLD` | 3 | 連続失敗でスキップする閾値 |
| `ONECO_AUTO_FIX_ENABLED` / `_DRY_RUN` / `_MAX_SITES` | false / true / 3 | [自己修復](04-self-healing.md) の段階リリース制御 |
| `RETENTION_DAYS` | 180 | archive へ移動するまでの日数 |
| `SLACK_WEBHOOK_URL` / `DISCORD_WEBHOOK_URL` | — | アラート通知先 |

### フロントエンド（`frontend/.env.local`）

| 変数 | 説明 |
|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | バックエンド API の URL |
| `NEXT_PUBLIC_SITE_URL` | 公開 URL（OGP 等） |
| `AUTH_SECRET` / `AUTH_GITHUB_ID` / `AUTH_GITHUB_SECRET` | Auth.js（admin ログイン） |
| `ADMIN_GITHUB_LOGIN` | /admin を許可する GitHub ユーザー名 |
| `INTERNAL_API_TOKEN` / `BACKEND_INTERNAL_URL` | admin からの内部 API 呼び出し |

## 開発ルール（要点）

- main 直コミット禁止。feature ブランチ + PR
- TDD: 実装前にテスト（Red → Green）
- `Animal` / `AnimalData` / `AnimalArchive` を触るときはルート `CLAUDE.md` の「Repository-specific Rules」を必読（サイレントドロップ再発防止）
- サイト追加の手順は [Adapter アーキテクチャ](03-adapters.md)
