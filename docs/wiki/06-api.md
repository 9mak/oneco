# REST API

FastAPI アプリは `infrastructure/api/app.py` の `create_app()` で構築。ルートは `routes.py` / `admin_routes.py` / syndication ルーター（`/feeds` prefix）で構成される。ローカルでは http://localhost:8000/docs で Swagger UI が見られる。

## 公開エンドポイント（`infrastructure/api/routes.py`）

| メソッド / パス | 内容 |
|---|---|
| `GET /animals` | 一覧。ページング + フィルタ（species / sex / location / prefecture / category / status / q / sort） |
| `GET /animals/{id}` | 個体詳細 |
| `GET /animals/stats/by-prefecture` | 都道府県別件数（トップページの日本地図用） |
| `GET /public/stats` | 公開統計 |
| `GET /archive` / `GET /archive/{id}` | アーカイブ一覧・詳細 |
| `GET /health` | ヘルスチェック（uptime-check が 30 分毎に監視） |

## フィード（`syndication_service`、`/feeds` prefix）

| パス | 内容 |
|---|---|
| `GET /feeds/rss` / `GET /feeds/atom` | 稼働中個体のフィード |
| `GET /feeds/archive/rss` | アーカイブのフィード |

⚠️ prefix に注意: `/rss` ではなく `/feeds/rss`（`app.py` で `prefix="/feeds"` マウント）。

## 内部・管理エンドポイント

| パス | 認証 | 内容 |
|---|---|---|
| ステータス更新（PATCH 系） | `INTERNAL_API_TOKEN`（`require_internal_token`） | 個体の status 変更 |
| `/admin/*`（`admin_routes.py`） | frontend 側で GitHub OAuth（`ADMIN_GITHUB_LOGIN` 許可制） | stats・サイトカバレッジ・site health |

## セキュリティ構成

- Supabase の anon ロールは SELECT を含む全権限を剥奪済み（alembic の Supabase セキュリティ系マイグレーション）。**DB へのアクセスは Cloud Run の API 経由のみ**
- CORS は `CORS_ORIGINS` 環境変数で制御
- 公開 API の rate limit は SSR exempt 設計が整うまで意図的に未導入（実トラフィック発生で再評価）
