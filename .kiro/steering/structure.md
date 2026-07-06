# Project Structure

モノレポ（Python バックエンド + Next.js フロントエンド）。

## Directory Map

```
oneco/
├── src/
│   ├── data_collector/          # 中核: 収集・正規化・保存・公開 API
│   │   ├── __main__.py          # CLI エントリ (python -m data_collector)
│   │   ├── adapters/            # スクレイピング adapter
│   │   │   ├── municipality_adapter.py   # 抽象基底 (ABC)
│   │   │   └── rule_based/      # base.py + 中間基底 + sites/*.py (93ファイル)
│   │   ├── domain/              # models / normalizer (PII伏字) / diff_detector
│   │   ├── infrastructure/      # database / api (FastAPI) / notification_client
│   │   ├── orchestration/       # collector_service / parallel_runner
│   │   ├── llm/                 # Groq フォールバック (通常収集では未使用)
│   │   ├── services/            # archive_service / scheduler
│   │   └── config/sites.yaml    # 全211サイト定義
│   ├── syndication_service/     # RSS/Atom (/feeds) + sns_publisher (Threads)
│   └── notification_manager/    # LINE 通知 (実装済み・本番未配線)
├── frontend/                    # Next.js 16 App Router (Vercel)
│   ├── app/                     # ルーティング (/, /animals/[id], /areas/, /admin ...)
│   └── lib/                     # animals.ts (API fetch) ほかドメインロジック
├── tests/                       # pytest (adapters/ は PYTHONPATH=src 必要)
├── alembic/                     # DB マイグレーション (14本)
├── scripts/                     # auto_fix_adapter.py / adapter_live_test.py / monitoring/
├── data/                        # run 跨ぎ状態 (broken_sites / baselines / sns_posts) ※Actions が自動コミット
├── snapshots/ output/           # 収集結果 ※Actions が自動コミット
├── docs/
│   ├── wiki/                    # 体系ドキュメント (索引: docs/wiki/README.md)
│   ├── RUNBOOK.md               # 障害対応ランブック
│   └── sns-launch/              # SNS アカウント設定記録
├── .github/workflows/           # 全9本 (CI 2 + デプロイ 1 + 定期 4 + 自己修復 2)
└── .kiro/                       # steering + specs (spec-driven development)
```

## Key Patterns

- **adapter 追加**: `sites.yaml` エントリ + `rule_based/sites/<site>.py` 実装 + `SiteAdapterRegistry.register()` + end-to-end テスト。手順は `docs/wiki/03-adapters.md`
- **1ファイル複数登録**: 1 adapter ファイルが複数 site_name（収容犬/収容猫等）を register するため、ファイル数(93) < sites.yaml エントリ数(211)
- **Animal ⇔ AnimalArchive 同期**: `animals` に新カラムを足すときは `animals_archive` にも同時に追加（後付け移行不可）。ルート CLAUDE.md の再発防止ルール参照
- **import 規約の混在**: `tests/adapters/` は `from data_collector...`（PYTHONPATH=src 必要）、`tests/domain/test_normalizer.py` は `from src.data_collector...`（不要）

## Naming Conventions

- サイト adapter: `city_<市名>.py` / `pref_<県名>.py` / `<団体名>_<県名>.py`（例: `city_kawasaki.py`, `pref_osaka.py`, `douai_tokushima.py`）
- Feature 名 (.kiro/specs/): kebab-case（例: `public-web-portal`）
- ブランチ: feature ブランチ必須（main 直コミット禁止）。自己修復 PR は `fix/auto-*` + `auto-fix` ラベル

---
_created_at: 2026-01-06_
_updated_at: 2026-07-06_
