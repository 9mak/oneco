# Technical Design Document: Collection Ops Dashboard

## 1. Overview

Collection Ops Dashboard は、oneco の全国 209+ サイト収集パイプラインの健全性を可視化する管理画面と、Phase 2 訴求用の公開メトリクスページの 2 系統を、既存の Next.js 16 App Router フロントエンドと FastAPI バックエンドに統合する形で実装する。

主要な設計判断：

- **認証**: Supabase Auth（既存の Supabase 連携を活用、追加サービス不要）+ Next.js Middleware
- **データソース**: 既存 PostgreSQL を真実の源とし、新規 3 テーブル（`llm_usage_logs`, `site_run_logs`, `animals_daily_aggregate`）を追加
- **集計戦略**: 重い集計は Postgres ビュー / Materialized View で実装、API は薄く保つ
- **チャート**: Recharts（既存実装と整合、SSR-safe）
- **公開メトリクス OG**: Next.js の `@vercel/og` 互換 ImageResponse でランタイム生成

## 2. Architecture Pattern & Boundary Map

```
┌─────────────────────────────────────────────────────────────────┐
│                      Next.js 16 App Router                       │
│                                                                  │
│  ┌────────────────────┐   ┌──────────────────────────────────┐  │
│  │  /admin/* (private)│   │  /stats (public)                 │  │
│  │   ├─ ServerComp   │   │   ├─ ServerComp (RSC)            │  │
│  │   ├─ Recharts (CC)│   │   ├─ OG endpoint                 │  │
│  │   └─ SWR auto-30s │   │   └─ ISR (revalidate=300)        │  │
│  └─────────┬──────────┘   └─────────────┬────────────────────┘  │
│            │                            │                        │
│            │ Middleware (auth gate)     │                        │
│            ▼                            ▼                        │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │   API Routes: /api/admin/*, /api/public/stats              │ │
│  │   (Route Handlers, server-only, Supabase JWT verify)       │ │
│  └─────────────────────────┬──────────────────────────────────┘ │
└────────────────────────────┼────────────────────────────────────┘
                             │ Service-to-Service (signed JWT)
┌────────────────────────────┼────────────────────────────────────┐
│                            ▼                                     │
│                   FastAPI Backend                                │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ /api/admin/*  (JWT-protected)                              │ │
│  │   ├─ sites/status, sites, sites/failure-ranking            │ │
│  │   ├─ animals/timeseries                                    │ │
│  │   ├─ llm/usage                                             │ │
│  │   └─ _health                                               │ │
│  ├────────────────────────────────────────────────────────────┤ │
│  │ /api/public/stats  (no auth, CORS open)                    │ │
│  └─────────────────────────┬──────────────────────────────────┘ │
└────────────────────────────┼────────────────────────────────────┘
                             ▼
                  ┌──────────────────────┐
                  │  PostgreSQL (Supabase)│
                  │   ├─ animals (existing)│
                  │   ├─ site_run_logs ★  │
                  │   ├─ llm_usage_logs ★ │
                  │   └─ animals_daily_   │
                  │      aggregate (MV) ★ │
                  └──────────────────────┘
                             ▲
                             │ writes
                  ┌──────────┴───────────┐
                  │  Data Collector       │
                  │   (existing, extended) │
                  └──────────────────────┘
```

★ = 新規追加

### 境界の根拠

- **Next.js / FastAPI の責務分割**: 既存 `public-web-portal` の設計に揃え、Next は UI と認証ゲート、FastAPI はビジネスロジックと DB アクセス。クロスオリジン JWT で連携。
- **Materialized View での集計**: 47 都道府県 × 30 日 = 1410 行程度。リアルタイム計算でも秒以下だが、ダッシュボード自動更新 30s/回 で 209 サイト × N 集計を全件読みだすと負荷が高い。MV で 1 回計算してキャッシュ。

## 3. Technology Stack & Alignment

| 層 | 採用技術 | 根拠 |
|---|---|---|
| 認証 | Supabase Auth + Next.js Middleware | 既存 Supabase 連携あり、JWT も既知 |
| Server Component fetch | Native `fetch` + Next.js cache | RSC 標準パターン、既存 portal と整合 |
| Client グラフ | Recharts | SSR-safe、既存基盤に親和的、TypeScript 完備 |
| OG 画像 | Next.js `ImageResponse` (Edge) | Next.js 14+ で標準、外部サービス不要 |
| バックエンド | FastAPI (既存) | 既存 syndication_service の slowapi 構成と整合 |
| DB ORM | asyncpg + SQL 直書き / 既存 Repository | 既存パターン踏襲、Materialized View 利用のため ORM 不要 |
| デプロイ | Cloud Run (FastAPI), Vercel (Next) | 既存と同じ |

## 4. Components & Interface Contracts

### 4.1 Frontend

**`frontend/middleware.ts`（既存を拡張）**

```ts
export async function middleware(req: NextRequest): Promise<NextResponse> {
  const pathname = req.nextUrl.pathname;
  if (pathname.startsWith("/admin")) {
    const session = await getSupabaseSession(req); // typed Session | null
    if (!session) {
      return NextResponse.redirect(new URL("/login", req.url));
    }
  }
  return NextResponse.next();
}
```

**`app/admin/layout.tsx`** — 認証必須レイアウト、ナビゲーション
**`app/admin/page.tsx`** — ダッシュボードトップ（6 パネル合成）
**`app/admin/sites/[siteName]/page.tsx`** — サイト別ドリルダウン
**`app/stats/page.tsx`** — 公開メトリクス（ISR, revalidate=300）
**`app/stats/og.png/route.ts`** — OG 画像エンドポイント

各パネルは `components/admin/panels/<Name>Panel.tsx` で独立 Server Component。データ取得は SWR で 30s ポーリング。

### 4.2 Backend (FastAPI)

新規モジュール: `src/admin_api/`

```python
# src/admin_api/routes.py（抜粋、型のみ）
class SiteStatus(BaseModel):
    site_name: str
    prefecture: str
    last_run_at: datetime | None
    status: Literal["success", "failure", "skipped", "stale", "unknown"]
    last_count: int | None
    last_error: str | None
    last_duration_sec: float | None

@router.get("/api/admin/sites/status", response_model=list[SiteStatus])
async def list_site_status(...) -> list[SiteStatus]: ...

class TimeseriesPoint(BaseModel):
    date: date
    prefecture: str | None  # None for all
    count: int

@router.get("/api/admin/animals/timeseries", response_model=list[TimeseriesPoint])
async def timeseries(prefecture: str | None, frm: date, to: date, ...): ...

class LlmUsage(BaseModel):
    provider: Literal["groq", "anthropic"]
    period: Literal["today", "month", "all"]
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float

@router.get("/api/admin/llm/usage", response_model=list[LlmUsage])
async def llm_usage(...): ...

class FailureRow(BaseModel):
    site_name: str
    failure_count: int
    failure_rate: float
    top_reason: Literal["rate_limit", "parse_error", "network", "timeout", "other"]

@router.get("/api/admin/sites/failure-ranking", response_model=list[FailureRow])
async def failure_ranking(days: int = 7, limit: int = 10): ...

class PublicStats(BaseModel):
    total_animals: int
    municipality_count: int
    site_count: int
    avg_waiting_days: float | None

@router.get("/api/public/stats", response_model=PublicStats)
async def public_stats(): ...
```

### 4.3 Data Collector への変更（最小）

既存 `CollectorService.run_collection` の終了時に以下を追加：

```python
# 1. site_run_logs に書き込み
await db.execute(
    "INSERT INTO site_run_logs (site_name, run_at, success, count, duration_sec, error_category, error_message) VALUES (...)"
)

# 2. LlmProvider が tokens を返すので、その時点で llm_usage_logs に書き込み
#    (FallbackProvider / GroqProvider / AnthropicProvider の generate() 戻り値に usage を追加)
```

`LlmProvider.generate` の戻り値を `(text, usage: TokenUsage)` の tuple に変更（型安全）。

## 5. Data Model

### 5.1 新規テーブル

```sql
-- site_run_logs: 各サイトの 1 回の収集試行を 1 行
CREATE TABLE site_run_logs (
    id BIGSERIAL PRIMARY KEY,
    site_name TEXT NOT NULL,
    prefecture TEXT NOT NULL,
    run_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    success BOOLEAN NOT NULL,
    count INT NOT NULL DEFAULT 0,
    duration_sec REAL NOT NULL,
    error_category TEXT,  -- 'rate_limit' | 'parse_error' | 'network' | 'timeout' | 'other'
    error_message TEXT
);
CREATE INDEX idx_site_run_logs_site_run_at ON site_run_logs (site_name, run_at DESC);
CREATE INDEX idx_site_run_logs_run_at ON site_run_logs (run_at DESC);

-- llm_usage_logs: 各 LLM 呼び出し
CREATE TABLE llm_usage_logs (
    id BIGSERIAL PRIMARY KEY,
    site_name TEXT NOT NULL,
    provider TEXT NOT NULL,  -- 'groq' | 'anthropic'
    model TEXT NOT NULL,
    prompt_tokens INT NOT NULL,
    completion_tokens INT NOT NULL,
    cost_usd NUMERIC(10, 6) NOT NULL DEFAULT 0,
    called_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_llm_usage_called_at ON llm_usage_logs (called_at DESC);
CREATE INDEX idx_llm_usage_provider_called_at ON llm_usage_logs (provider, called_at DESC);

-- animals_daily_aggregate: 都道府県 × 日付の件数 (Materialized View)
CREATE MATERIALIZED VIEW animals_daily_aggregate AS
SELECT
    DATE(updated_at AT TIME ZONE 'Asia/Tokyo') AS date,
    prefecture,
    COUNT(*) AS count
FROM animals
GROUP BY 1, 2;
CREATE UNIQUE INDEX idx_animals_daily_aggregate ON animals_daily_aggregate (date, prefecture);

-- 日次 refresh (CONCURRENTLY で本番影響なし)
-- Data Collector が GitHub Actions 末尾で REFRESH MATERIALIZED VIEW CONCURRENTLY を実行
```

### 5.2 マイグレーション

Alembic で 1 つの migration ファイル `xxx_add_ops_dashboard_tables.py` に集約。既存 `_supabase_roles_exist()` ガード（PR #4 で導入済）と整合させる。

## 6. API Contracts (詳細)

### `GET /api/admin/sites/status`

- **認証**: JWT 必須
- **クエリパラメータ**: なし
- **レスポンス**: `SiteStatus[]` （209 件程度）
- **集計クエリ**:
  ```sql
  SELECT DISTINCT ON (site_name)
    site_name, prefecture, run_at AS last_run_at,
    CASE WHEN success THEN 'success'
         WHEN run_at < now() - interval '36 hours' THEN 'stale'
         ELSE 'failure' END AS status,
    count AS last_count, error_message AS last_error,
    duration_sec AS last_duration_sec
  FROM site_run_logs
  ORDER BY site_name, run_at DESC;
  ```

### `GET /api/admin/animals/timeseries`

- **クエリ**: `prefecture` (optional), `from` (date), `to` (date)
- **レスポンス**: `TimeseriesPoint[]`
- **データソース**: `animals_daily_aggregate`

### `GET /api/admin/llm/usage`

- **レスポンス**: `LlmUsage[]` (provider × period の組合せ)
- **集計**:
  ```sql
  SELECT provider,
         SUM(prompt_tokens), SUM(completion_tokens), SUM(cost_usd)
  FROM llm_usage_logs
  WHERE called_at >= :start
  GROUP BY provider;
  ```

### `GET /api/public/stats`

- **認証**: 不要
- **CORS**: `*`
- **キャッシュ**: HTTP `Cache-Control: public, max-age=300`
- **レスポンス**:
  ```json
  {
    "total_animals": 1234,
    "municipality_count": 42,
    "site_count": 209,
    "avg_waiting_days": 28.5
  }
  ```

## 7. Security

- **管理 API**: Supabase JWT を Authorization ヘッダで受け取り、FastAPI 側で公開鍵検証（Supabase の JWKS エンドポイント）。`role: admin` claim を必須にする
- **ロール管理**: Supabase の `auth.users` に追加した `app_metadata.admin: true` で判定
- **CSRF**: Server Component fetch は same-origin、Client Component の mutation は今回想定なし（ReadOnly）
- **公開 API**: `/api/public/stats` は ReadOnly、Rate Limit 60req/min/IP（slowapi）

## 8. Performance

- **SLO**: P95 < 1s (admin API), < 500ms (public stats)
- **キャッシュ層**:
  - admin: SWR client cache + Postgres MV
  - public: HTTP cache + Next.js ISR (revalidate=300s)
- **ボトルネック想定**: `animals_daily_aggregate` の MV refresh。CONCURRENTLY で読み取りを止めない。GitHub Actions 末尾で 1 日 1 回 refresh

## 9. Testing Strategy

| 層 | フレームワーク | カバレッジ目標 |
|---|---|---|
| FastAPI route | pytest + httpx | 90% (新規モジュール) |
| Data Collector log writer | pytest | 既存 collector_service との結合テスト |
| Next.js panels | vitest + Testing Library | レンダリング + SWR モック |
| E2E | Playwright | /admin ログインフロー + 各パネル表示 |
| a11y | @axe-core/playwright | 0 violation（WCAG AA） |
| Performance | Lighthouse CI | Performance ≥80, A11y =100 |

## 10. Operability

- **ロギング**: 既存 FastAPI ミドルウェアで JSON 出力、`request_id` を全 admin API レスポンスに付与
- **メトリクス**: `_health` エンドポイントで panel 別エラー率を返却、Slack 通知（10% 超で WARN）は cron で別途実装
- **MV refresh の監視**: 失敗時 Slack 通知
- **デプロイ順**: ① DB migration（Alembic）② FastAPI ③ Next.js（順に zero-downtime）

## 11. Risks & Mitigations

| リスク | 影響 | 対策 |
|---|---|---|
| Supabase Auth の JWT 互換性 | admin API が全滅 | 統合テストで JWKS 鍵ローテーション込みで検証 |
| 209 サイトの MV refresh が長時間化 | ダッシュボードが古いデータを表示 | CONCURRENTLY + Slack 監視 |
| 公開 stats の DDoS | API 過負荷 | slowapi で 60/min/IP、CF キャッシュ |
| LLM コスト集計の誤算 | 予算判断ミス | テストで provider 別の単価ロジックを単体検証 |
| 既存 frontend a11y 退行 | WCAG 退行 | E2E a11y を必須化、CI gate |

## 12. Requirements Traceability

| Req | 対応コンポーネント |
|---|---|
| 1.1–1.6 | `middleware.ts`, `/api/admin/*` JWT verify |
| 2.1–2.6 | SitesStatusPanel + `/api/admin/sites/status` |
| 3.1–3.6 | TimeseriesPanel + `/api/admin/animals/timeseries` + MV |
| 4.1–4.6 | LlmUsagePanel + `/api/admin/llm/usage` + `llm_usage_logs` |
| 5.1–5.5 | FailureRankingPanel + `/api/admin/sites/failure-ranking` + `site_run_logs` |
| 6.1–6.5 | SitesListPanel + `/api/admin/sites` + sites.yaml パーサ |
| 7.1–7.6 | SWR 30s ポーリング, P95 SLO 監視 |
| 8.1–8.6 | `/stats` page + `/api/public/stats` + OG endpoint |
| 9.1–9.5 | a11y test, responsive layout, focus indicator |
| 10.1–10.5 | 構造化ログ, panel-level error boundary, `_health` endpoint |
