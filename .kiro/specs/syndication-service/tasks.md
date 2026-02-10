# Implementation Plan: syndication-service

## Task Overview

以下の実装タスクは、syndication-service の要件と設計に基づいて生成されています。各タスクは型安全性、エラーハンドリング、テスト容易性を重視し、段階的に機能を構築します。

**実装順序**: 基盤セットアップ → サービス層 → API層 → キャッシング・レート制限 → 統合・テスト

---

## Tasks

### 1. プロジェクトセットアップと依存関係追加

- [x] 1.1 (P) 依存関係を requirements.txt に追加
  - feedgen（python-feedgen）を追加し、RSS 2.0 / Atom 1.0 フィード生成機能を提供
  - fastapi-cache2 と redis[asyncio] を追加し、非同期 Redis キャッシング機能を提供
  - slowapi を追加し、IP ベースレート制限機能を提供
  - 各ライブラリのバージョンを固定（feedgen>=1.0.0, fastapi-cache2>=0.2.0, slowapi>=0.1.9）
  - _Requirements: 1.1, 1.2, 4.1, 8.1_

- [x] 1.2 (P) Redis 開発環境をセットアップ
  - Docker Compose で Redis コンテナを追加（redis:7-alpine）
  - ポート 6379 を公開し、ローカル開発環境からアクセス可能にする
  - 環境変数 REDIS_URL のデフォルト値を docker-compose.yml に設定（redis://localhost:6379/0）
  - Redis 接続確認コマンドを README に追加
  - _Requirements: 4.1, 4.2, 8.1_

- [x] 1.3 (P) syndication_service ディレクトリ構造を作成
  - src/syndication_service/ ディレクトリを作成
  - サブディレクトリ: services/, api/, models/ を作成
  - __init__.py ファイルを各ディレクトリに追加
  - _Requirements: 全般_

### 2. FeedGenerator サービス実装

- [x] 2.1 (P) FeedGenerator 基本クラスを実装
  - python-feedgen の FeedGenerator インスタンスを初期化
  - AnimalData リストとフィルタ条件を入力として受け取る
  - RSS 2.0 と Atom 1.0 の両方をサポート（generate_rss, generate_atom メソッド）
  - _Requirements: 1.1, 1.2_

- [x] 2.2 RSS 2.0 フィード生成機能を実装
  - チャンネル情報（title, link, description, lastBuildDate, ttl）を設定
  - フィルタ条件をタイトルと説明に反映（例: 「保護動物情報 - 犬 / 高知県」）
  - TTL タグに 3600（1時間）を設定
  - _Requirements: 1.4, 3.6_

- [x] 2.3 RSS アイテム生成機能を実装
  - 各動物データを <item> タグに変換
  - タイトル（種別 + 地域）、リンク（source_url）、説明（詳細情報）、pubDate（shelter_date）を設定
  - GUID を source_url の MD5 ハッシュで生成（isPermaLink="false"）
  - 画像 URL が存在する場合、<enclosure> タグを追加
  - _Requirements: 1.3, 1.7, 3.5_

- [x] 2.4 Atom 1.0 フィード生成機能を実装
  - フィード情報（title, subtitle, link, id, updated）を設定
  - Atom の <id> タグを tag: URI スキームで生成（例: tag:example.com,2026-02-02:/feeds/atom）
  - _Requirements: 1.5_

- [x] 2.5 Atom エントリ生成機能を実装
  - 各動物データを <entry> タグに変換
  - タイトル、リンク、id（tag: URI）、summary、published、updated を設定
  - 画像 URL が存在する場合、<link rel="enclosure"> タグを追加
  - _Requirements: 1.3, 1.7_

- [x] 2.6 XML エスケープ処理と CDATA セクション対応を実装
  - 特殊文字（<, >, &, ", '）を XML エスケープ
  - HTML タグを含む説明フィールドを CDATA セクションでラップ
  - _Requirements: 9.6, 9.7_

- [x] 2.7 フィード生成エラーハンドリングを実装
  - source_url 欠損時に FeedGenerationError を発生
  - python-feedgen の例外を適切にハンドリング
  - エラーログを記録（ERROR レベル、スタックトレース含む）
  - _Requirements: 5.6_

### 3. CacheManager サービス実装

- [x] 3.1 (P) CacheManager 基本クラスを実装
  - Redis 接続 URL を環境変数から取得（REDIS_URL）
  - redis.asyncio.Redis クライアントを初期化
  - キャッシュキー生成メソッド（_generate_cache_key）を実装
  - ETag 生成メソッド（_generate_etag）を実装（キャッシュキーの MD5 ハッシュ）
  - _Requirements: 4.3, 4.6_

- [x] 3.2 キャッシュ取得機能を実装
  - get_cached_feed メソッドを実装（format, filter_params, if_none_match を引数）
  - Redis から GET コマンドでフィード XML を取得
  - If-None-Match ヘッダーと ETag を比較し、一致時は is_304=True を返却
  - キャッシュミス時は (None, None, False) を返却
  - _Requirements: 4.2, 4.7_

- [x] 3.3 キャッシュ保存機能を実装
  - save_cached_feed メソッドを実装（format, filter_params, feed_xml を引数）
  - Redis に SETEX コマンドでフィード XML を保存（TTL: 300秒）
  - 生成した ETag を返却
  - _Requirements: 4.1, 4.4_

- [x] 3.4 Redis 障害時の graceful degradation を実装
  - Redis 接続失敗時に例外をキャッチ
  - キャッシュ取得/保存をスキップし、警告ログを記録
  - 通常のフィード生成処理を継続（キャッシュなしで動作）
  - _Requirements: 5.1, 5.2_

### 4. InputValidator サービス実装

- [x] 4.1 (P) InputValidator クラスを実装
  - クエリパラメータの有効値を定数で定義（VALID_SPECIES, VALID_CATEGORY, VALID_STATUS, VALID_SEX）
  - validate_query_params メソッドを実装
  - _Requirements: 8.6_

- [x] 4.2 (P) クエリパラメータ長チェックを実装
  - URL クエリ文字列の合計長を計算
  - 1000文字を超える場合、HTTP 400 エラーを発生
  - エラーメッセージ「リクエストURLが長すぎます」を含める
  - _Requirements: 8.4, 8.5_

- [x] 4.3 (P) 悪意のある文字列検出を実装
  - クエリパラメータ値に <, >, script, SELECT, DROP 等の文字列が含まれる場合、HTTP 400 エラーを発生
  - エラーメッセージ「無効なパラメータ: {key}」を含める
  - _Requirements: 8.6_

- [x] 4.4 (P) 有効値チェックを実装
  - species, category, status, sex の各パラメータが有効値リストに含まれるか検証
  - 無効値の場合、HTTP 400 エラーを発生
  - _Requirements: 2.1, 2.2, 2.4, 2.5_

### 5. MetricsCollector サービス実装

- [x] 5.1 (P) MetricsCollector クラスを実装
  - フィード生成数、キャッシュヒット/ミス、レスポンスタイムを記録
  - メモリ内カウンターと配列でメトリクスを保持
  - record_feed_generation, record_cache_hit, record_cache_miss, record_response_time メソッドを実装
  - _Requirements: 7.5, 7.6, 7.7_

- [x] 5.2 (P) メトリクス集計機能を実装
  - get_metrics_snapshot メソッドを実装
  - 1時間あたりのフィード生成数を計算
  - キャッシュヒット率（ヒット数 / 総リクエスト数）を計算
  - レスポンスタイム（p50, p95, p99）を numpy.percentile で計算
  - _Requirements: 7.5, 7.6, 7.7_

### 6. SyndicationRouter 実装（通常フィード）

- [x] 6.1 FeedQueryParams スキーマを定義
  - species, category, location, status, sex, limit パラメータを Pydantic モデルで定義
  - Query バリデーション（limit: 1~100, デフォルト50）を設定
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2_

- [x] 6.2 GET /feeds/rss エンドポイントを実装
  - FeedQueryParams を受け取り、InputValidator でバリデーション
  - CacheManager でキャッシュチェック（キャッシュヒット時は即座に返却）
  - キャッシュミス時: AnimalRepository でデータ取得 → FeedGenerator で RSS 生成
  - CacheManager にフィード XML を保存
  - Content-Type: application/rss+xml; charset=utf-8 ヘッダーを設定
  - _Requirements: 1.1, 1.6, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 3.1, 3.2, 3.3_

- [x] 6.3 GET /feeds/atom エンドポイントを実装
  - GET /feeds/rss と同様のフローで Atom フィードを生成
  - Content-Type: application/atom+xml; charset=utf-8 ヘッダーを設定
  - _Requirements: 1.2, 1.6, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 3.1, 3.2, 3.3_

- [x] 6.4 Cache-Control と ETag ヘッダーを設定
  - Cache-Control: public, max-age=300 ヘッダーを全レスポンスに追加
  - ETag ヘッダーに CacheManager から取得した ETag を設定
  - If-None-Match ヘッダーチェックで 304 Not Modified を返却
  - _Requirements: 4.5, 4.6, 4.7_

- [x] 6.5 空フィード処理を実装
  - フィルタ条件に該当する動物が存在しない場合、0件のアイテムを含むフィードを生成
  - HTTP 200 ステータスコードを返却
  - _Requirements: 2.7_

### 7. SyndicationRouter 実装（アーカイブフィード）

- [x] 7.1 (P) ArchiveFeedQueryParams スキーマを定義
  - species, location, archived_from, archived_to, limit パラメータを Pydantic モデルで定義
  - 日付パラメータのバリデーション（date 型）を設定
  - _Requirements: 6.5, 6.6_

- [x] 7.2 GET /feeds/archive/rss エンドポイントを実装
  - ArchiveFeedQueryParams を受け取り、ArchiveRepository でデータ取得
  - FeedGenerator でアーカイブフィード（feed_type="archive"）を生成
  - アイテムの公開日に archived_at を使用
  - フィードタイトルに「保護動物アーカイブ - [条件]」を設定
  - _Requirements: 6.1, 6.3, 6.4, 6.5, 6.6, 6.7_

- [x] 7.3 GET /feeds/archive/atom エンドポイントを実装
  - GET /feeds/archive/rss と同様のフローで Atom アーカイブフィードを生成
  - _Requirements: 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_

### 8. RateLimiter ミドルウェアとレート制限実装

- [x] 8.1 (P) slowapi Limiter を初期化
  - app.py で Limiter インスタンスを作成（key_func=get_remote_address, storage_uri=REDIS_URL）
  - app.state.limiter として登録
  - Redis 障害時のフォールバック処理（レート制限を無効化し、警告ログ記録）
  - _Requirements: 8.1_

- [x] 8.2 (P) レート制限を全フィードエンドポイントに適用
  - @limiter.limit("60/minute") デコレータを各エンドポイントに追加
  - X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset ヘッダーを自動設定（slowapi が処理）
  - _Requirements: 8.2, 8.3_

- [x] 8.3 (P) レート制限超過時のエラーレスポンスを実装
  - HTTP 429 Too Many Requests エラーを返却
  - Retry-After ヘッダーに再試行可能時刻を設定
  - エラーメッセージ「レート制限を超過しました」を含める
  - _Requirements: 8.2_

### 9. HealthCheckRouter 実装

- [x] 9.1 (P) HealthCheckResponse スキーマを定義
  - status, timestamp, upstream_api_status, cache_status, metrics フィールドを Pydantic モデルで定義
  - MetricsSnapshot スキーマを定義
  - _Requirements: 7.4_

- [x] 9.2 (P) GET /health エンドポイントを実装
  - Redis 接続確認（PING コマンド）を実施
  - AnimalRepository でデータベース接続確認（SELECT 1 クエリ）を実施
  - 両方成功時: status="healthy", 200 OK を返却
  - いずれか失敗時: status="unhealthy", 503 Service Unavailable を返却
  - MetricsCollector から現在のメトリクスを取得し、レスポンスに含める
  - _Requirements: 7.1, 7.2, 7.3, 7.4_

### 10. 既存 FastAPI アプリへの統合

- [x] 10.1 syndication_router を app.py に登録
  - src/data_collector/infrastructure/api/app.py で syndication_router をインポート
  - app.include_router(syndication_router, prefix="/feeds", tags=["syndication"]) を追加
  - Limiter を app.state.limiter に登録
  - _Requirements: 全般_

- [x] 10.2 環境変数設定を README に追加
  - REDIS_URL のデフォルト値と設定方法を記載
  - 開発環境と本番環境の設定例を記載
  - _Requirements: 全般_

### 11. エラーハンドリングとログ記録統合

- [ ] 11.1 (P) エラーハンドラーを実装
  - animal-api-persistence API タイムアウト時（3秒超過）: HTTP 504 Gateway Timeout エラーを返却
  - animal-api-persistence API 5xx エラー時: HTTP 502 Bad Gateway エラーを返却
  - animal-api-persistence API 404 エラー時: 空のフィードを生成し HTTP 200 を返却
  - 不正なフィルタパラメータ時: HTTP 400 Bad Request エラーを返却
  - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [ ] 11.2 (P) 構造化ログ記録を実装
  - 既存の logging_config.py を再利用
  - 全リクエストをログ記録（リクエストURL, フィルタ条件, レスポンスタイム, キャッシュヒット/ミス, エラー内容）
  - エラー発生時は ERROR レベルでログ記録（スタックトレース、リクエストコンテキスト含む）
  - ログフォーマット: ISO 8601 タイムスタンプ、ログレベル、モジュール名、メッセージ
  - _Requirements: 5.5, 5.6, 5.7_

- [ ] 11.3 (P) レスポンスタイム計測ミドルウェアを実装
  - FastAPI ミドルウェアで各リクエストのレスポンスタイムを計測
  - MetricsCollector.record_response_time() を呼び出し
  - _Requirements: 7.7_

### 12. テスト実装

- [ ] 12.1 (P) FeedGenerator ユニットテストを実装
  - RSS 2.0 フィード生成の正確性テスト（チャンネル情報、アイテム、enclosure タグ）
  - Atom 1.0 フィード生成の正確性テスト（feed/entry 要素、id 形式）
  - XML エスケープ処理テスト（特殊文字の正しいエスケープ）
  - CDATA セクション生成テスト
  - 空リスト（0件）のフィード生成テスト
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.7, 9.6, 9.7_

- [ ] 12.2 (P) CacheManager ユニットテストを実装
  - キャッシュキー生成の一意性テスト（異なるフィルタで異なるキー）
  - ETag 生成の一貫性テスト（同じキーで同じ ETag）
  - If-None-Match 一致時の 304 判定テスト
  - Redis 障害時の graceful degradation テスト
  - _Requirements: 4.3, 4.6, 4.7, 5.1_

- [ ] 12.3 (P) InputValidator ユニットテストを実装
  - 有効値チェックテスト（species, category, status, sex）
  - URL 長制限チェックテスト（1000文字超過で 400）
  - 悪意のある文字列検出テスト（XSS, SQLi パターン）
  - _Requirements: 8.4, 8.5, 8.6_

- [ ] 12.4 SyndicationRouter 統合テストを実装
  - GET /feeds/rss エンドポイントのE2Eテスト（DB → フィード生成 → XML 返却）
  - フィルタリング機能テスト（species, category, location, status, sex の組み合わせ）
  - ページネーション機能テスト（limit パラメータ）
  - アーカイブフィードテスト（/feeds/archive/rss）
  - _Requirements: 1.1, 1.2, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 3.1, 3.2, 6.1, 6.2_

- [ ] 12.5 キャッシング統合テストを実装
  - キャッシュミス → DB クエリ → キャッシュ保存のフローテスト
  - キャッシュヒット → Redis から取得 → XML 返却のフローテスト
  - ETag 一致 → 304 Not Modified 返却のフローテスト
  - Redis 障害時のフォールバックフローテスト
  - _Requirements: 4.1, 4.2, 4.4, 4.5, 4.7_

- [ ] 12.6 レート制限統合テストを実装
  - レート制限超過時の 429 エラーテスト
  - X-RateLimit-* ヘッダーの検証
  - _Requirements: 8.1, 8.2, 8.3_

- [ ] 12.7* W3C Feed Validator 検証テスト
  - 生成された RSS 2.0 フィードを W3C Feed Validator で検証
  - 生成された Atom 1.0 フィードを W3C Feed Validator で検証
  - 検証エラーがないことを確認
  - _Requirements: 9.1, 9.2_

- [ ] 12.8* RSS リーダー互換性テスト
  - 実際の RSS リーダー（Feedly, Inoreader）で購読テスト
  - 画像の正しい表示を確認
  - _Requirements: 1.7, 9.1, 9.2_

### 13. パフォーマンステスト

- [ ] 13.1* キャッシュヒット時レスポンスタイムテスト
  - 同一条件で10回リクエストし、平均レスポンスタイムを計測
  - 目標: 50ms 以内
  - _Requirements: 10.1_

- [ ] 13.2* キャッシュミス時レスポンスタイムテスト
  - 異なる条件で10回リクエスト（キャッシュミス発生）し、平均レスポンスタイムを計測
  - 目標: 500ms 以内
  - _Requirements: 10.2_

- [ ] 13.3* 同時100リクエスト負荷テスト
  - Apache Bench または Locust で100並列リクエストを実行
  - タイムアウトやエラー発生率を確認
  - 目標: タイムアウト0件、エラー率 < 1%
  - _Requirements: 10.4_

- [ ] 13.4* 大量アイテム（100件）フィード生成時間テスト
  - limit=100 でフィード生成時間を計測
  - 目標: 1秒以内
  - _Requirements: 10.3_

---

## Requirements Coverage Matrix

| Requirement | Covered by Tasks |
|-------------|------------------|
| 1.1 | 1.1, 2.1, 6.2, 12.1 |
| 1.2 | 1.1, 2.1, 6.3, 12.1 |
| 1.3 | 2.3, 2.5, 12.1 |
| 1.4 | 2.2, 12.1 |
| 1.5 | 2.4, 12.1 |
| 1.6 | 6.2, 6.3 |
| 1.7 | 2.3, 2.5, 12.1, 12.8* |
| 2.1 | 4.4, 6.1, 6.2, 6.3, 12.4 |
| 2.2 | 4.4, 6.1, 6.2, 6.3, 12.4 |
| 2.3 | 6.1, 6.2, 6.3, 12.4 |
| 2.4 | 4.4, 6.1, 6.2, 6.3, 12.4 |
| 2.5 | 4.4, 6.1, 6.2, 6.3, 12.4 |
| 2.6 | 6.2, 6.3, 12.4 |
| 2.7 | 6.2, 6.3, 6.5, 12.4 |
| 2.8 | 6.2, 6.3, 12.4 |
| 3.1 | 6.1, 6.2, 6.3, 12.4 |
| 3.2 | 6.1, 6.2, 6.3, 12.4 |
| 3.3 | 6.2, 6.3 |
| 3.4 | (RSS/Atom 標準仕様に従う) |
| 3.5 | 2.3 |
| 3.6 | 2.2 |
| 4.1 | 1.1, 1.2, 3.3, 12.5 |
| 4.2 | 1.2, 3.2, 12.5 |
| 4.3 | 3.1 |
| 4.4 | 3.3, 12.5 |
| 4.5 | 6.4, 12.5 |
| 4.6 | 3.1, 6.4, 12.2 |
| 4.7 | 3.2, 6.4, 12.2, 12.5 |
| 5.1 | 3.4, 11.1, 12.2 |
| 5.2 | 3.4, 11.1 |
| 5.3 | 11.1 |
| 5.4 | 11.1 |
| 5.5 | 11.2 |
| 5.6 | 2.7, 11.2 |
| 5.7 | 11.2 |
| 6.1 | 7.2, 12.4 |
| 6.2 | 7.3, 12.4 |
| 6.3 | 7.2, 7.3 |
| 6.4 | 7.2, 7.3 |
| 6.5 | 7.1, 7.2, 7.3 |
| 6.6 | 7.1, 7.2, 7.3 |
| 6.7 | 7.2, 7.3 |
| 7.1 | 9.2 |
| 7.2 | 9.2 |
| 7.3 | 9.2 |
| 7.4 | 9.1, 9.2 |
| 7.5 | 5.1, 5.2 |
| 7.6 | 5.1, 5.2 |
| 7.7 | 5.1, 5.2, 11.3 |
| 8.1 | 1.1, 1.2, 8.1, 12.6 |
| 8.2 | 8.2, 8.3, 12.6 |
| 8.3 | 8.2, 12.6 |
| 8.4 | 4.2, 12.3 |
| 8.5 | 4.2, 12.3 |
| 8.6 | 4.1, 4.3, 12.3 |
| 8.7 | (本番環境設定で対応) |
| 9.1 | 12.7*, 12.8* |
| 9.2 | 12.7*, 12.8* |
| 9.3 | (RSS/Atom 標準仕様に従う) |
| 9.4 | (RSS/Atom 標準仕様に従う) |
| 9.5 | (RSS/Atom 標準仕様に従う) |
| 9.6 | 2.6, 12.1 |
| 9.7 | 2.6, 12.1 |
| 10.1 | 13.1* |
| 10.2 | 13.2* |
| 10.3 | 13.4* |
| 10.4 | 13.3* |
| 10.5 | (本番環境モニタリングで確認) |
| 10.6 | (設計で対応済み) |

**合計**: 13 major tasks, 47 sub-tasks (うち optional: 7)

---

_タスク生成日: 2026-02-02_
