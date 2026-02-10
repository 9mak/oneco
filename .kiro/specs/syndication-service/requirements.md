# Requirements Document

## Project Description (Input)
syndication-service: 条件別RSSフィード生成サービス。ユーザー指定条件（種別、地域等）に基づく動的フィード出力により、外部ツールやRSSリーダーでの購読を可能にする。

## Introduction

syndication-service は、保護動物データを RSS/Atom フィードとして外部配信するサービスです。既存の REST API（animal-api-persistence）を活用し、ユーザーが指定したフィルタ条件（種別、カテゴリ、地域、ステータス等）に基づいて動的にフィードを生成します。これにより、RSS リーダーや外部サービス（IFTTT、Zapier 等）を通じた自動通知や他サイトへの埋め込みが可能になります。

### 主要ユースケース
- **RSS リーダー購読**: ユーザーが特定条件（例: 高知県の犬）の新着情報を RSS リーダーで受信
- **外部サービス連携**: IFTTT/Zapier 経由で新規保護動物の自動通知（メール、Slack 等）
- **サイト埋め込み**: 外部ウェブサイトが特定条件のフィードを埋め込み表示
- **アーカイブ購読**: 譲渡済み動物の RSS フィード購読（成果追跡）

### システム境界
- **入力**: ユーザー指定のフィルタ条件（URLクエリパラメータ）
- **処理**: REST API へのクエリ実行、RSS/Atom フォーマット変換
- **出力**: RSS 2.0 / Atom 1.0 準拠の XML フィード

## Requirements

### Requirement 1: RSS/Atom フィード基本生成機能
**Objective:** As a ユーザー, I want 保護動物データを RSS/Atom フィード形式で取得したい, so that RSS リーダーや外部サービスで購読できる

#### Acceptance Criteria
1. When ユーザーが `/feeds/rss` エンドポイントにアクセス, the Syndication Service shall animal-api-persistence の `GET /animals` API からデータを取得し RSS 2.0 準拠の XML フィードを返却
2. When ユーザーが `/feeds/atom` エンドポイントにアクセス, the Syndication Service shall animal-api-persistence の `GET /animals` API からデータを取得し Atom 1.0 準拠の XML フィードを返却
3. The Syndication Service shall フィード内の各 item/entry に以下の情報を含める: タイトル（種別 + 地域）、説明（詳細情報）、リンク（元ページ URL）、公開日（収容日）、GUID（source_url のハッシュ値）
4. The Syndication Service shall RSS 2.0 フィードのチャンネル情報に、タイトル「保護動物情報 - [条件]」、説明「条件に合致する保護動物の情報」、リンク（フィード自身の URL）を含める
5. The Syndication Service shall Atom 1.0 フィードに、feed/title、feed/subtitle、feed/link、feed/id、feed/updated を含める
6. The Syndication Service shall `Content-Type: application/rss+xml; charset=utf-8` (RSS) または `Content-Type: application/atom+xml; charset=utf-8` (Atom) ヘッダーを返却
7. When フィード生成時に画像URLが存在, the Syndication Service shall RSS の `<enclosure>` タグまたは Atom の `<link rel="enclosure">` タグで画像を含める

### Requirement 2: フィルタリング条件対応
**Objective:** As a ユーザー, I want フィード取得時に条件を指定したい, so that 興味のある動物のみを購読できる

#### Acceptance Criteria
1. When ユーザーが `?species=犬` クエリパラメータを指定, the Syndication Service shall animal-api-persistence API に `species=犬` パラメータを渡して犬のみのフィードを生成
2. When ユーザーが `?category=adoption` クエリパラメータを指定, the Syndication Service shall 譲渡対象動物のみのフィードを生成
3. When ユーザーが `?location=高知` クエリパラメータを指定, the Syndication Service shall location フィールドに「高知」を含む動物のみのフィードを生成
4. When ユーザーが `?status=sheltered` クエリパラメータを指定, the Syndication Service shall 収容中の動物のみのフィードを生成
5. When ユーザーが `?sex=男の子` クエリパラメータを指定, the Syndication Service shall 性別が「男の子」の動物のみのフィードを生成
6. When ユーザーが複数のフィルタを同時指定（例: `?species=犬&location=高知&category=adoption`）, the Syndication Service shall 全条件を AND で結合してフィードを生成
7. When フィルタ条件に該当する動物が存在しない, the Syndication Service shall 空のフィード（0件の item/entry）を返却し HTTP 200 ステータスコードを返す
8. The Syndication Service shall フィードのタイトルと説明に適用されたフィルタ条件を反映（例: 「保護動物情報 - 犬 / 高知県」）

### Requirement 3: ページネーションとフィード更新頻度
**Objective:** As a ユーザー, I want フィードが適切な件数と更新頻度で配信される, so that RSS リーダーでのパフォーマンスが最適化される

#### Acceptance Criteria
1. The Syndication Service shall デフォルトで最新 50 件の動物データをフィードに含める
2. When ユーザーが `?limit=100` クエリパラメータを指定, the Syndication Service shall 指定された件数（最大 100 件）のデータをフィードに含める
3. If limit が 100 を超える値を指定, the Syndication Service shall HTTP 400 Bad Request エラーを返し、「limit は 100 以下にしてください」というメッセージを含める
4. The Syndication Service shall RSS/Atom フィードの `<lastBuildDate>` / `<updated>` タグに現在時刻（フィード生成時刻）を ISO 8601 形式で設定
5. The Syndication Service shall フィード内のアイテムを収容日（`shelter_date`）の降順でソート（最新の動物が先頭）
6. The Syndication Service shall `<ttl>` タグ（RSS）に 3600（1時間）を設定し、RSS リーダーに 1 時間ごとの更新チェックを推奨

### Requirement 4: キャッシング機能
**Objective:** As a システム管理者, I want フィード生成処理がキャッシュされる, so that animal-api-persistence への負荷を軽減できる

#### Acceptance Criteria
1. The Syndication Service shall 同一条件のフィード生成結果を 5 分間キャッシュ
2. When キャッシュ有効期間内に同一条件のリクエストを受信, the Syndication Service shall キャッシュからフィードを返却し、animal-api-persistence API を呼び出さない
3. The Syndication Service shall キャッシュキーとしてフィルタ条件（species, category, location, status, sex, limit）の組み合わせを使用
4. When キャッシュ有効期間が経過, the Syndication Service shall 次回リクエスト時に animal-api-persistence API を再度呼び出してキャッシュを更新
5. The Syndication Service shall HTTP レスポンスヘッダー `Cache-Control: public, max-age=300` を返却し、クライアント側キャッシュを許可
6. The Syndication Service shall HTTP レスポンスヘッダー `ETag` にキャッシュキーのハッシュ値を含め、`If-None-Match` による条件付きリクエストをサポート
7. When クライアントが `If-None-Match` ヘッダーで有効な ETag を送信, the Syndication Service shall HTTP 304 Not Modified を返却しボディを省略

### Requirement 5: エラーハンドリングとログ記録
**Objective:** As a システム管理者, I want フィード生成エラーが適切に処理され記録される, so that 問題の診断と対処が容易になる

#### Acceptance Criteria
1. If animal-api-persistence API がタイムアウト（5秒超過）, the Syndication Service shall HTTP 504 Gateway Timeout エラーを返し、「上流サービスがタイムアウトしました」というメッセージを含める
2. If animal-api-persistence API が 5xx エラーを返却, the Syndication Service shall HTTP 502 Bad Gateway エラーを返し、「上流サービスでエラーが発生しました」というメッセージを含める
3. If animal-api-persistence API が 404 エラーを返却, the Syndication Service shall 空のフィードを生成し HTTP 200 ステータスコードを返す
4. If 不正なフィルタパラメータを受信（例: `species=不正値`）, the Syndication Service shall HTTP 400 Bad Request エラーを返し、「無効なパラメータ: species」というメッセージを含める
5. The Syndication Service shall 全リクエストのログを記録（リクエスト URL、フィルタ条件、レスポンスタイム、キャッシュヒット/ミス、エラー内容）
6. When エラーが発生, the Syndication Service shall ERROR レベルのログを記録し、スタックトレースとリクエストコンテキストを含める
7. The Syndication Service shall ログフォーマットに ISO 8601 タイムスタンプ、ログレベル、モジュール名、メッセージを含める

### Requirement 6: アーカイブフィード生成
**Objective:** As a ユーザー, I want 譲渡済み/返還済み動物のフィードを購読したい, so that 保護動物の成果を追跡できる

#### Acceptance Criteria
1. When ユーザーが `/feeds/archive/rss` エンドポイントにアクセス, the Syndication Service shall animal-api-persistence の `GET /archive/animals` API からデータを取得し RSS 2.0 フィードを生成
2. When ユーザーが `/feeds/archive/atom` エンドポイントにアクセス, the Syndication Service shall animal-api-persistence の `GET /archive/animals` API からデータを取得し Atom 1.0 フィードを生成
3. The Syndication Service shall アーカイブフィードのタイトルに「保護動物アーカイブ - [条件]」を設定
4. The Syndication Service shall アーカイブフィード内の各 item/entry の公開日に `archived_at`（アーカイブ日時）を使用
5. The Syndication Service shall アーカイブフィードで `?species`, `?location`, `?archived_from`, `?archived_to` フィルタパラメータをサポート
6. When ユーザーが `?archived_from=2026-01-01` パラメータを指定, the Syndication Service shall 指定日以降にアーカイブされた動物のみを含める
7. The Syndication Service shall アーカイブフィードのアイテムを `archived_at` の降順でソート（最近アーカイブされた動物が先頭）

### Requirement 7: ヘルスチェックとメトリクス
**Objective:** As a システム管理者, I want サービス稼働状況を監視できる, so that 障害の早期検知と対応が可能になる

#### Acceptance Criteria
1. When ユーザーが `/health` エンドポイントにアクセス, the Syndication Service shall サービスの稼働状態（status: "healthy" / "degraded" / "unhealthy"）を JSON 形式で返却
2. The Syndication Service shall ヘルスチェックで animal-api-persistence API への接続確認を実施
3. If animal-api-persistence API への接続が失敗, the Syndication Service shall status を "unhealthy" に設定し HTTP 503 Service Unavailable を返却
4. The Syndication Service shall ヘルスチェックレスポンスに以下の情報を含める: status、timestamp、upstream_api_status（"ok" / "error"）、cache_status（"ok" / "error"）
5. The Syndication Service shall 1時間あたりのフィード生成数を記録
6. The Syndication Service shall キャッシュヒット率（ヒット数 / 総リクエスト数）を計算
7. The Syndication Service shall フィード生成処理の平均レスポンスタイム（p50, p95, p99）を記録

### Requirement 8: セキュリティとレート制限
**Objective:** As a システム管理者, I want 悪用を防止する, so that サービスの安定性を確保できる

#### Acceptance Criteria
1. The Syndication Service shall 同一 IP アドレスからのリクエストを 1 分あたり 60 回に制限
2. When レート制限を超過, the Syndication Service shall HTTP 429 Too Many Requests エラーを返し、`Retry-After` ヘッダーに再試行可能時刻を設定
3. The Syndication Service shall `X-RateLimit-Limit`、`X-RateLimit-Remaining`、`X-RateLimit-Reset` ヘッダーを全レスポンスに含める
4. The Syndication Service shall クエリパラメータの最大長を 1000 文字に制限
5. If クエリパラメータが 1000 文字を超過, the Syndication Service shall HTTP 400 Bad Request エラーを返し、「リクエスト URL が長すぎます」というメッセージを含める
6. The Syndication Service shall 悪意のある文字列（SQL インジェクション、XSS 等）をクエリパラメータから検出した場合、HTTP 400 Bad Request エラーを返却
7. The Syndication Service shall HTTPS のみをサポートし、HTTP リクエストを HTTPS にリダイレクト（本番環境のみ）

### Requirement 9: フィード検証とバリデーション
**Objective:** As a ユーザー, I want 生成されたフィードが RSS/Atom 標準に準拠している, so that 全ての RSS リーダーで正しく表示される

#### Acceptance Criteria
1. The Syndication Service shall RSS 2.0 フィードが W3C Feed Validator で検証可能な形式で生成
2. The Syndication Service shall Atom 1.0 フィードが RFC 4287 に準拠
3. The Syndication Service shall XML 宣言 `<?xml version="1.0" encoding="utf-8"?>` を全フィードの先頭に含める
4. The Syndication Service shall RSS の `<guid>` タグに `isPermaLink="false"` 属性を設定し、source_url のハッシュ値をユニーク識別子として使用
5. The Syndication Service shall Atom の `<id>` タグに `tag:` URI スキーム（例: `tag:example.com,2026-01-01:/animals/{hash}`）を使用
6. The Syndication Service shall 特殊文字（`<`, `>`, `&`, `"`, `'`）を XML エスケープ処理
7. When 動物の説明に HTML タグが含まれる, the Syndication Service shall `<description>` / `<summary>` タグを CDATA セクションでラップ

### Requirement 10: パフォーマンス要件
**Objective:** As a システム管理者, I want フィード生成が高速である, so that ユーザー体験が良好になる

#### Acceptance Criteria
1. The Syndication Service shall キャッシュヒット時のレスポンスタイムを 50ms 以内に維持
2. The Syndication Service shall キャッシュミス時のレスポンスタイムを 500ms 以内に維持（animal-api-persistence API の応答時間を含む）
3. The Syndication Service shall 100 件のアイテムを含むフィードを 1 秒以内に生成
4. The Syndication Service shall 同時 100 リクエストを処理可能（非同期処理）
5. The Syndication Service shall メモリ使用量を 512MB 以下に維持（本番環境）
6. When animal-api-persistence API からのレスポンスが 3 秒を超過, the Syndication Service shall タイムアウト処理を実行し HTTP 504 エラーを返却

---

## Requirements Coverage Summary

| 要件エリア | 要件数 | 主要機能 |
|-----------|--------|---------|
| フィード生成 | 7 | RSS/Atom 基本生成、画像埋め込み |
| フィルタリング | 8 | 種別、カテゴリ、地域、ステータス、性別 |
| ページネーション | 6 | 件数制限、ソート、更新頻度 |
| キャッシング | 7 | 5分キャッシュ、ETag、条件付きリクエスト |
| エラーハンドリング | 7 | タイムアウト、5xx/4xx エラー、ログ記録 |
| アーカイブフィード | 7 | アーカイブ API 連携、日付フィルタ |
| ヘルスチェック | 7 | 稼働監視、メトリクス記録 |
| セキュリティ | 7 | レート制限、パラメータ検証、HTTPS |
| フィード検証 | 7 | RSS/Atom 標準準拠、XML エスケープ |
| パフォーマンス | 6 | レスポンスタイム、同時接続数 |

**合計**: 69 の受け入れ基準

---

_生成日: 2026-02-02_
