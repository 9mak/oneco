# データフロー

収集からフロントエンド表示までの一連の流れ。ファイルパスは実装箇所。

## 全体の流れ

```
config/sites.yaml (211サイト定義)
  → run_rule_based_sites() / run_llm_sites()        [__main__.py]
  → CollectorService.run_collection()               [orchestration/collector_service.py]
       ├ adapter が一覧/詳細ページを取得（ドメイン単位 politeness throttle）
       ├ adapter.normalize(raw) → DataNormalizer.normalize()   [domain/normalizer.py]
       ├ DiffDetector で新規/更新判定（snapshot 比較）          [domain/diff_detector.py]
       ├ AnimalRepository.save_animal() で upsert              [infrastructure/database/repository.py]
       ├ OutputWriter → output/animals.json
       └ SnapshotStore → snapshots/latest.json
  → FastAPI GET /animals ほか                        [infrastructure/api/routes.py]
  → frontend lib/animals.ts fetchAnimals()
  → 各ページで表示（ISR/SSG）
```

## 正規化（`domain/normalizer.py`）

- **PII 伏字**: 自由記述（description）内の電話番号・メールアドレスを `███` に置換（`_PII_PHONE_RE` / `_PII_EMAIL_RE`）。`management_number` は誤伏字を避けるため PII 処理を適用しない
- **画像フィルタ**: アイコン等のジャンク URL を除去（`_filter_valid_image_urls`）
- **値の正規化**: species は「犬/猫/その他」、sex は「男の子/女の子/不明」に強制。`age_months` の妥当性チェック

⚠️ **サイレントドロップ注意**: `Animal` / `RawAnimalData` / `AnimalData` / `AnimalArchive` を触る変更は、過去に `breed/name/management_number/description` の欠落を6回繰り返した経緯がある。ルート `CLAUDE.md` の「Repository-specific Rules」と PR テンプレートのチェックリストに必ず従うこと。

## 保存（`infrastructure/database/repository.py`）

- `save_animal()` は `source_url` を一意キーに **upsert**。既存レコードは status / status_changed_at を更新
- `prune_disappeared()` でサイトから消えた個体を処理
- 180日経過した個体は `ArchiveService` が `animals_archive` へ移動（→ [データベース](05-database.md)）

## run 跨ぎ状態ファイル（`data/`、Actions が自動コミット）

| ファイル | 役割 |
|---|---|
| `data/broken_sites.yaml` | 連続失敗カウンタ。閾値3で自動スキップ（`BrokenSitesTracker`） |
| `data/site_baselines.yaml` | サイト別件数ベースライン。「過去≥1件 → 今0件」のゼロ回帰検知 |
| `data/field_quality_drift.yaml` | フィールド欠損率ドリフト検知（`FieldQualityTracker`） |
| `data/sns_posts.yaml` | SNS 投稿ログ（重複投稿防止） |

**自動コミットの仕組み**: `data-collector.yml` の最終ステップが `output/animals.json`・`snapshots/latest.json`・`data/*.yaml` を `github-actions[bot]` でコミット（message: `Update collection data [automated]`）。push 衝突時は `git pull --rebase` で最大3回リトライ。run 冒頭で snapshot/output を `reset()` して fresh state から開始する。

## robots.txt の尊重

`_apply_robots_policy()`（`__main__.py`）が収集前に robots.txt を確認し、disallow サイトをスキップ、Crawl-delay をリクエスト間隔に反映する。rule-based / LLM 両経路で共有。
