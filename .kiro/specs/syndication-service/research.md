# Research & Design Decisions

---
**Purpose**: syndication-service の設計判断と技術調査結果を記録

**Usage**:
- 軽量ディスカバリー実施（既存システム拡張）
- RSS/Atom ライブラリとキャッシング戦略の調査
- animal-api-persistence との統合ポイント分析
---

## Summary
- **Feature**: `syndication-service`
- **Discovery Scope**: Extension（既存 animal-api-persistence API への薄い統合レイヤー）
- **Key Findings**:
  - python-feedgen を使用した RSS 2.0 / Atom 1.0 標準準拠フィード生成
  - FastAPI + Redis による2層キャッシング戦略（アプリ層 + HTTP層）
  - 既存 FastAPI アプリとの統合（別ルーター追加またはマイクロサービス化）

## Research Log

### RSS/Atom フィード生成ライブラリ選定

- **Context**: Python で RSS 2.0 / Atom 1.0 標準準拠フィードを生成する必要がある
- **Sources Consulted**:
  - [python-feedgen GitHub](https://github.com/lkiesow/python-feedgen)
  - [python-feedgen Documentation](https://feedgen.kiesow.be/)
  - [RSS 2.0 Specification](https://www.rssboard.org/rss-specification)
  - [RFC 4287: Atom Syndication Format](https://datatracker.ietf.org/doc/html/rfc4287)
- **Findings**:
  - **python-feedgen**: 活発にメンテナンスされている標準ライブラリ
    - RSS 2.0 / Atom 1.0 両対応
    - `<enclosure>` タグ（画像）サポート
    - 拡張可能（Podcast 等）
    - PyPI パッケージ: `feedgen`
  - **代替案**: feedparser（読み込み専用）、django-contrib-syndication（Django専用）
- **Implications**:
  - python-feedgen を採用し、FeedGenerator API でフィード構築
  - RSS の `<guid isPermaLink="false">` と Atom の `<id>` に source_url のハッシュ値を使用

### FastAPI キャッシング戦略

- **Context**: フィード生成処理の負荷軽減と高速化が必要（要件4: 5分キャッシュ、ETag サポート）
- **Sources Consulted**:
  - [FastAPI Caching Guide - Redis, ETag](https://blog.greeden.me/en/2025/09/17/blazing-fast-rock-solid-a-complete-fastapi-caching-guide-redis-http-caching-etag-rate-limiting-and-compression/)
  - [fastapi-cache2 PyPI](https://pypi.org/project/fastapi-cache2/)
  - [fastapi-etag PyPI](https://pypi.org/project/fastapi-etag/)
  - [RSS Feed Caching Best Practices](https://www.ctrl.blog/entry/feed-caching.html)
- **Findings**:
  - **2層キャッシング戦略**:
    1. **アプリ層（Redis）**: 5分 TTL でフィード XML を Redis に保存
    2. **HTTP層（ETag + Cache-Control）**: クライアント側キャッシュと 304 Not Modified レスポンス
  - **ETag 生成**: フィルタ条件のハッシュ値を使用（URL + クエリパラメータ）
  - **Cache-Control**: `public, max-age=300`（5分）
  - **ライブラリ**:
    - `fastapi-cache2`: Redis バックエンドサポート、デコレータベース
    - `aioredis` または `redis[asyncio]`: 非同期 Redis クライアント
- **Implications**:
  - Redis を依存に追加（環境変数 `REDIS_URL`）
  - fastapi-cache2 の `@cache` デコレータで各エンドポイントをラップ
  - `Response` ヘッダーに `ETag` と `Cache-Control` を手動設定
  - `If-None-Match` ヘッダーチェックで 304 返却

### 既存 FastAPI アプリケーションとの統合

- **Context**: animal-api-persistence は FastAPI で実装済み（app.py 確認済み）
- **Sources Consulted**:
  - 既存コード: `src/data_collector/infrastructure/api/app.py`
  - 既存ルート: `src/data_collector/infrastructure/api/routes.py`
- **Findings**:
  - **現在の構成**:
    - FastAPI アプリ: `create_app()` 関数で初期化
    - ルーター: `router` と `archive_router` を登録
    - CORS 設定済み（環境変数 `CORS_ORIGINS`）
  - **統合オプション**:
    1. **同一アプリ内ルーター追加**: `/feeds` ルーターを `app.include_router()` で追加（推奨）
    2. **別マイクロサービス**: 独立した FastAPI アプリを別ポートで起動
- **Implications**:
  - **選択**: 同一アプリ内ルーター追加（シンプル、デプロイ容易）
  - 新規ファイル: `src/syndication_service/api/routes.py`
  - `app.py` に `syndication_router` を追加登録
  - 環境変数: `REDIS_URL`, `ANIMAL_API_BASE_URL`（内部呼び出し用、localhost）

### レート制限実装

- **Context**: 要件8: IP ベースレート制限（60 req/min）
- **Sources Consulted**:
  - [slowapi PyPI](https://pypi.org/project/slowapi/)
  - [FastAPI rate limiting](https://github.com/laurentS/slowapi)
- **Findings**:
  - **slowapi**: FastAPI 用レート制限ライブラリ
    - Redis バックエンドサポート
    - `X-RateLimit-*` ヘッダー自動設定
    - IP アドレスベース制限
  - **使用方法**: `@limiter.limit("60/minute")` デコレータ
- **Implications**:
  - slowapi を依存に追加
  - Limiter インスタンスを app.py で初期化（Redis 共有）

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| 同一アプリ内ルーター | `/feeds` ルーターを既存 FastAPI アプリに追加 | シンプル、デプロイ容易、DB接続共有 | animal-api ダウン時に syndication も影響 | 推奨：シンプルで保守性高い |
| 別マイクロサービス | syndication-service を独立 FastAPI アプリとして起動 | 障害分離、独立スケーリング | デプロイ複雑化、httpx での内部呼び出し必要 | 過剰設計（現時点） |
| プロキシパターン | syndication が animal-api を httpx で呼び出し | 完全分離、API コントラクト明確 | ネットワークホップ増加、レイテンシ悪化 | 将来的に検討 |

**選択**: 同一アプリ内ルーター（Option 1）

## Design Decisions

### Decision: python-feedgen によるフィード生成

- **Context**: RSS 2.0 / Atom 1.0 標準準拠フィードを動的生成する必要がある
- **Alternatives Considered**:
  1. **python-feedgen** — 標準ライブラリ、RSS/Atom両対応、活発なメンテナンス
  2. **feedparser** — 読み込み専用、生成機能なし
  3. **手動XML生成** — 標準準拠が困難、保守コスト高
- **Selected Approach**: python-feedgen
  - FeedGenerator インスタンスを作成
  - チャンネル/フィード情報設定（title, link, description）
  - 各動物データを `add_entry()` でアイテム追加
  - `rss_str()` / `atom_str()` で XML 文字列を取得
- **Rationale**:
  - W3C Feed Validator / RFC 4287 準拠が保証される
  - 画像埋め込み（`<enclosure>`）が標準サポート
  - コミュニティで広く使用されている
- **Trade-offs**:
  - **Benefits**: 標準準拠、保守性高、実装コスト低
  - **Compromises**: ライブラリ依存追加（軽量）
- **Follow-up**: 生成フィードを W3C Feed Validator でテスト

### Decision: Redis + fastapi-cache2 による2層キャッシング

- **Context**: animal-api-persistence への負荷軽減と高速化（要件4, 10）
- **Alternatives Considered**:
  1. **Redis + fastapi-cache2** — 非同期対応、デコレータベース、ETag 自動生成可能
  2. **In-memory caching (cachetools)** — Redis 不要だが、複数インスタンスで一貫性なし
  3. **CDN キャッシング** — 外部依存、設定複雑
- **Selected Approach**:
  - Redis を共有キャッシュストアとして使用
  - fastapi-cache2 の `@cache(expire=300)` でエンドポイントをラップ
  - キャッシュキー: `feed_type:filter_hash`（例: `rss:abc123`）
  - ETag: フィルタ条件のハッシュ値（MD5）
  - HTTP ヘッダー: `Cache-Control: public, max-age=300`, `ETag: "abc123"`
- **Rationale**:
  - 複数インスタンス間でキャッシュ共有
  - 非同期処理と FastAPI との統合が自然
  - ETag + 304 Not Modified でネットワーク帯域削減
- **Trade-offs**:
  - **Benefits**: 高速レスポンス（50ms目標）、負荷軽減、スケーラビリティ
  - **Compromises**: Redis インフラ依存、キャッシュ無効化戦略が必要
- **Follow-up**:
  - 新規動物データ追加時のキャッシュ無効化戦略（TTL依存 or 明示的削除）
  - Redis 接続失敗時のフォールバック（キャッシュなしで動作）

### Decision: 同一 FastAPI アプリ内に `/feeds` ルーターを追加

- **Context**: 既存 animal-api-persistence FastAPI アプリとの統合方法
- **Alternatives Considered**:
  1. **同一アプリ内ルーター** — シンプル、DB接続共有
  2. **別マイクロサービス** — 障害分離、独立デプロイ
  3. **プロキシパターン** — httpx で内部呼び出し
- **Selected Approach**:
  - `src/syndication_service/api/routes.py` に新規ルーター作成
  - `app.py` の `create_app()` で `app.include_router(syndication_router, prefix="/feeds")`
  - AnimalRepository を直接使用（httpx 経由ではなく、DB直接アクセス）
- **Rationale**:
  - デプロイが単純（単一アプリ）
  - DB 接続プールを共有（リソース効率）
  - ネットワークホップなし（低レイテンシ）
  - 将来的に分離可能（ルーターを別アプリに移行するだけ）
- **Trade-offs**:
  - **Benefits**: シンプル、低レイテンシ、保守容易
  - **Compromises**: animal-api 障害時に syndication も影響（許容範囲）
- **Follow-up**: 将来的にトラフィック増加時、マイクロサービス化を検討

## Risks & Mitigations

- **Risk 1**: Redis 障害時にフィード生成が完全停止
  - **Mitigation**: Redis 接続失敗時はキャッシュをスキップし、直接 DB から生成（graceful degradation）
- **Risk 2**: キャッシュされたフィードが古い情報を返す（5分遅延）
  - **Mitigation**: TTL を適切に設定（5分）、RSS の `<ttl>` タグで更新頻度を明示
- **Risk 3**: 大量のフィルタ条件でキャッシュキーが爆発
  - **Mitigation**: Redis の maxmemory-policy を allkeys-lru に設定し、古いキーを自動削除
- **Risk 4**: ETag 生成の衝突（異なる条件で同じハッシュ）
  - **Mitigation**: MD5 ハッシュは十分にユニーク（衝突確率は無視可能）
- **Risk 5**: slowapi レート制限が Redis 依存
  - **Mitigation**: Redis 障害時はレート制限を無効化し、ログ記録のみ

## References

- [python-feedgen GitHub](https://github.com/lkiesow/python-feedgen) — RSS/Atom 生成ライブラリ
- [python-feedgen Documentation](https://feedgen.kiesow.be/) — 公式ドキュメント
- [RFC 4287: Atom Syndication Format](https://datatracker.ietf.org/doc/html/rfc4287) — Atom 1.0 仕様
- [RSS 2.0 Specification](https://www.rssboard.org/rss-specification) — RSS 2.0 仕様
- [FastAPI Caching Guide](https://blog.greeden.me/en/2025/09/17/blazing-fast-rock-solid-a-complete-fastapi-caching-guide-redis-http-caching-etag-rate-limiting-and-compression/) — Redis + ETag 実装ガイド
- [fastapi-cache2 PyPI](https://pypi.org/project/fastapi-cache2/) — FastAPI キャッシングライブラリ
- [slowapi PyPI](https://pypi.org/project/slowapi/) — FastAPI レート制限ライブラリ
- [RSS Feed Caching Best Practices](https://www.ctrl.blog/entry/feed-caching.html) — フィードキャッシング推奨事項

---

_生成日: 2026-02-02_
