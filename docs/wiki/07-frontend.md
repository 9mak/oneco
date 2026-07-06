# フロントエンド

- **Next.js 16 App Router / React 19 / Tailwind CSS v4**（`frontend/package.json`）
- 認証: Auth.js v5（`frontend/auth.ts`、GitHub OAuth、admin 専用）
- 日本地図: `d3-geo` + `topojson-client`
- テスト: Vitest（unit）+ Playwright（E2E）+ a11y テスト
- デプロイ: **Vercel**（`main` push で自動。`frontend.yml` はテストのみ）

## ページ一覧（`frontend/app/`）

| ルート | レンダリング戦略 |
|---|---|
| `/`（トップ・一覧・日本地図） | ISR `revalidate = 300` |
| `/animals/[id]`（詳細 + OGP 画像） | 動的 |
| `/areas/[prefecture]`（県別） | **SSG force-static**。`generateStaticParams` で全 47 県をビルド時生成 |
| `/archive` | ISR `revalidate = 1800` |
| `/stats` | ISR `revalidate = 300` |
| `/favorites` | クライアントのみ（localStorage、`lib/favorites.ts`） |
| `/admin`, `/admin/sites` ほか | GitHub OAuth（`ADMIN_GITHUB_LOGIN` に一致するユーザーのみ） |
| `/about` `/privacy` `/terms` `/transparency` | 静的。transparency は `data/transparency-sites.json` |
| `sitemap.xml` | `force-dynamic`, `revalidate = 3600` |

## データ取得（`frontend/lib/animals.ts`）

- `fetchAnimals()` がバックエンド REST API を fetch。ベース URL は `NEXT_PUBLIC_API_BASE_URL`（既定 `http://localhost:8000`）
- Next の fetch キャッシュ（`next.revalidate`、既定 300 秒）で ISR を制御
- ドメインロジックは `frontend/lib/` に集約（`archive.ts` / `public-stats.ts` / `prefectures.ts` / `japan-map.ts` / `heatmap-bins.ts` / `admin.ts` / `social.ts` 等）

## ハマりどころ

- **`/areas/[日本語スラッグ]` × ISR の 500 事件**: ISR 再検証時に `x-next-cache-tags` ヘッダーの日本語スラッグが原因で 47 ページが 500 になった。PR #229 で force-static + `fetch revalidate:false` に変更して解消。uptime-check に `/areas/東京都` を含めているのはこの再発検知のため
- **画像ホストの列挙**: 新しい収集サイトの画像ホストは `next.config.ts` の `remotePatterns` に追加が必要。`tests/test_image_remote_patterns.py`（backend CI）が `sites.yaml` との一致を強制する。列挙漏れは silent failure になる（PR #179 の教訓）
- **ビルド時 API 依存**: SSG/`generateStaticParams` はビルド時にバックエンド API を叩くため、API 停止中は frontend ビルドが失敗しうる
