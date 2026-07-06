# フィード配信と SNS 投稿

`src/syndication_service/` が担当。①RSS/Atom フィード配信と ②Threads への日次自動投稿の2機能。

## フィード配信

- `services/feed_generator.py` の `FeedGenerator` が python-feedgen で RSS / Atom を生成（稼働中・アーカイブの2系統）
- `data_collector` の FastAPI に `/feeds` prefix でマウント → `/feeds/rss`, `/feeds/atom`, `/feeds/archive/rss`
- 付帯: `cache_manager.py`（キャッシュ）、`metrics_collector.py`、`middleware/rate_limiter.py`、`input_validator.py`

## SNS 自動投稿（Threads）

- エントリ: `python -m syndication_service.sns_publisher`（`sns-publish.yml` が毎日 JST 9:00 に実行）
- 中核: `sns_publisher/publisher.py` の `publish_one()`

### パイプライン

```
1. kill switch 確認   THREADS_PUBLISH_ENABLED (既定 false → 即終了)
2. 候補選定           candidate_selector.py
                      status=SHELTERED + 画像あり + deceased 除外 + 未投稿 (data/sns_posts.yaml)
3. 投稿文生成         text_generator.py
4. モデレーション      moderator.py（二重防御、下記）
5. dry_run 確認       THREADS_PUBLISH_DRY_RUN (既定 true → ログ記録のみ)
6. Threads API 投稿   threads_client.py
```

### 安全機構（4層防御）

| 層 | 内容 |
|---|---|
| kill switch | `THREADS_PUBLISH_ENABLED` 既定 false。repo variables で制御 |
| dry_run | `THREADS_PUBLISH_DRY_RUN` 既定 true。`sns-publish.yml` の `workflow_dispatch(dry_run_override)` で一時変更可 |
| モデレーター | normalizer の PII 伏字後に **再 grep**（電話/メール残留 → HARD reject）。status が deceased/adopted/returned も reject。文字数超過は truncate |
| post_log | `data/sns_posts.yaml` に投稿記録を残し重複投稿を防止（Actions が自動コミット） |

失敗理由は `PublishResult.reason` で分類される（`disabled` / `no_candidate` / `moderation_failed:*` / `dry_run` / `no_api_client` / `publish_error:*`）。

### 関連する監視

Threads トークンの silent 失効は `secret-health.yml`（日次）が検知して Discord に通知する（→ [監視](10-monitoring.md)）。SNS アカウント設定・申請の経緯は `docs/sns-launch/` を参照。
