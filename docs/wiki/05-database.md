# データベース

## 接続構成

- 本番: **Supabase PostgreSQL**（aws-1-ap-northeast-2）
- 接続は SQLAlchemy async + asyncpg（`infrastructure/database/connection.py`）
- **pgbouncer transaction-mode プーラー（port 6543）経由**（PR #233, 2026-07-05〜）
  - transaction モードでは prepared statement が使えないため、`statement_cache_size=0` を設定済み（`connection.py`）
  - session モード（:5432）で `EMAXCONNSESSION`（接続枯渇）が発生した教訓による移行
- ローカル: PostgreSQL（docker-compose）または SQLite（`oneco_local.db`）
  - ⚠️ ローカル SQLite と本番 Postgres にはスキーマ乖離がある（既知の技術的負債）

## テーブル（`infrastructure/database/models.py`）

### `animals` — 稼働中の個体

| カラム群 | 内容 |
|---|---|
| 識別 | `id` (PK), `source_url` (**unique** — upsert キー), `source_site` (index), `management_number` |
| 個体情報 | `species` (NOT NULL, index), `breed`, `name`, `sex`, `category`, `age_months`, `color`, `size`, `description` |
| 収容情報 | `shelter_date`, `location`, `prefecture`, `phone` |
| 状態 | `status` (既定 `sheltered`), `status_changed_at`, `outcome_date` |
| 画像 | `image_urls` (JSON), `local_image_paths` |

### `animal_status_history` — ステータス遷移の監査ログ

`animal_id` (FK) / `old_status` / `new_status` / `changed_at` / `changed_by`

### `animals_archive` — アーカイブ

- `animals` とほぼ同カラム + `original_id`（元の animals.id）+ `archived_at`
- `status_history` リレーションと `source_site` は持たない（簡素化）

⚠️ **`Animal` に新カラムを追加するときは `AnimalArchive` にも同時に追加する**こと。active から消えた個体は取り戻せないため、後付け移行は不可能（ルート CLAUDE.md 参照）。

### `image_hashes` — 画像重複排除

`hash` (unique) / `local_path` / `file_size`

## アーカイブ運用（`services/archive_service.py`)

保持期間（既定 180 日、`RETENTION_DAYS`）を超えた個体を `animals_archive` へ insert してから `animals` から delete。画像も `move_to_archive()`。フロントは `/archive` ページと API `/archive/*` で参照する。

※ ArchiveService の自動実行は apscheduler（`services/scheduler.py`）経由の設計で、GitHub Actions の専用 cron は存在しない。

## マイグレーション（`alembic/versions/`、14本）

```bash
alembic upgrade head
```

主なもの:
- `33c0ccd7c108` animals テーブル作成 / `8a9b0c1d2e3f` repository スキーマ
- `b8c9d0e1f2a3` + `c9d0e1f2a3b4` 個体識別フィールド（animals と archive をペアで追加）
- `7a8b9c0d1e2f` notification_manager テーブル
- Supabase セキュリティ系 5本: RLS 有効化・anon の write/select/USAGE 剥奪・GraphQL 非公開化（= DB へは Cloud Run 経由のみアクセス可能にする）

本番マイグレーションは `deploy-backend.yml` の `workflow_dispatch(run_migration)` トグル、または `data-collector.yml` の run 冒頭（`alembic upgrade head`）で適用される。
