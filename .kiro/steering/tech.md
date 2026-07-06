# Technology Stack

## Architecture

サーバーレス構成（固定費 ≒ 0 を維持する方針）:

- **収集**: GitHub Actions cron（毎日 JST 0:00）で `python -m data_collector` を実行
- **DB**: Supabase PostgreSQL。**pgbouncer transaction-mode プーラー (:6543)** 経由で接続（PR #233。session mode は EMAXCONNSESSION 枯渇の教訓により不使用。asyncpg は `statement_cache_size=0`）
- **API**: FastAPI を Google Cloud Run `oneco-api`（asia-northeast1）にデプロイ（WIF キーレス、`deploy-backend.yml`）
- **Frontend**: Next.js を Vercel にデプロイ（`main` push で自動。CF Pages は 2026-05-19 に全廃）

## Backend (Python 3.11)

- FastAPI / SQLAlchemy async + asyncpg / alembic
- スクレイピング: httpx + BeautifulSoup、JS 必須サイト(27件)は Playwright、PDF は pdfplumber
- **抽出はデフォルト rule-based**（サイト別 adapter、`sites.yaml` の `default_extraction: rule-based`）
- **LLM は Groq `llama-3.3-70b-versatile` のみ**。用途は adapter 自己修復（SEARCH/REPLACE 方式）と抽出フォールバック。**Anthropic API は不採用**（コスト方針）
- Lint: ruff（`check` + `format --check` の2段。CI で強制）。mypy は既知エラー約120件のためゲート無効

## Frontend

- Next.js 16 App Router / React 19 / Tailwind CSS v4 / Auth.js v5 (GitHub OAuth, admin 専用)
- ISR（トップ 300s / archive 1800s）+ SSG（`/areas/[prefecture]` は force-static、日本語スラッグ × ISR の 500 事件対策 PR #229）
- 画像ホストは `next.config.ts` の `remotePatterns` に列挙必須（`tests/test_image_remote_patterns.py` が sites.yaml との一致を CI で強制）

## Testing

- pytest + pytest-asyncio (strict)。実行は `.venv/bin/python`（Python 3.11、CI と一致）
- adapter/registry テストは `PYTHONPATH=src` が必要
- frontend: Vitest + Playwright E2E + a11y
- adapter の新規テストは `adapter.normalize(raw)` の戻り値 `AnimalData` でアサーションする（end-to-end 必須）

## Key Technical Decisions

1. **rule-based を default 抽出に**（2026-05-15）: LLM API コスト $0 維持。壊れたら adapter を直す
2. **自己修復ループ**（2026-06〜）: 検知(3トラッカー) → Groq で修復 PR → auto-merge。kill switch `ONECO_AUTO_FIX_ENABLED` 段階リリース
3. **収集データを git にコミット**: snapshot / broken_sites / baselines の履歴が git log に残る
4. **Supabase anon 権限全剥奪**: DB アクセスは Cloud Run API 経由のみ（RLS + REVOKE の alembic 5本）

詳細は `docs/wiki/`（アーキテクチャ・データフロー・adapter・監視ほか）を参照。

---
_created_at: 2026-01-06_
_updated_at: 2026-07-06_
