# 本番環境デプロイガイド

## 前提条件

- Docker & Docker Compose インストール済み
- PostgreSQL 15+（マネージドサービス推奨）
- Redis 7+（マネージドサービス推奨）
- ドメイン + SSL証明書

## デプロイ手順

### 1. 環境変数の設定

```bash
# .env.production.example をコピー
cp .env.production.example .env.production

# 必須項目を編集
vim .env.production
```

**必須の環境変数**:
- `POSTGRES_PASSWORD`: 強力なパスワードに変更
- `SECRET_KEY`: ランダムな秘密鍵を生成
- `CORS_ORIGINS`: フロントエンドのドメインを設定
- `LINE_CHANNEL_ACCESS_TOKEN`: LINE Messaging API トークン
- `LINE_CHANNEL_SECRET`: LINE チャネルシークレット

### 2. Docker イメージのビルド

```bash
# 本番用イメージをビルド
docker-compose -f docker-compose.prod.yml build

# ビルド結果を確認
docker images | grep oneco
```

### 3. データベースマイグレーション

```bash
# マイグレーションを実行
docker-compose -f docker-compose.prod.yml run --rm migration

# マイグレーション結果を確認
docker-compose -f docker-compose.prod.yml exec postgres \
  psql -U oneco -d oneco -c "\dt"
```

### 4. サービスの起動

```bash
# すべてのサービスを起動
docker-compose -f docker-compose.prod.yml up -d

# サービスの状態を確認
docker-compose -f docker-compose.prod.yml ps

# ログを確認
docker-compose -f docker-compose.prod.yml logs -f api
```

### 5. ヘルスチェック

```bash
# API ヘルスチェック
curl http://localhost:8000/health

# 動物データ取得テスト
curl http://localhost:8000/animals?limit=10

# OpenAPI ドキュメント確認
open http://localhost:8000/docs
```

## GitHub Actions CI/CD

### 必要なシークレット設定

GitHub リポジトリの Settings > Secrets and variables > Actions で以下を設定:

```
NOTIFICATION_EMAIL=admin@example.com
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
DATABASE_URL=postgresql+asyncpg://...
```

### 自動デプロイの有効化

1. `.github/workflows/backend.yml` を確認
2. `main` ブランチへのプッシュで自動実行
3. デプロイステップを追加（任意）

## モニタリング

### ログの確認

```bash
# API ログ
docker-compose -f docker-compose.prod.yml logs -f api

# PostgreSQL ログ
docker-compose -f docker-compose.prod.yml logs -f postgres

# Redis ログ
docker-compose -f docker-compose.prod.yml logs -f redis
```

### メトリクスの確認

```bash
# ヘルスチェック
curl http://localhost:8000/health

# データベース接続確認
docker-compose -f docker-compose.prod.yml exec postgres \
  psql -U oneco -d oneco -c "SELECT count(*) FROM animals;"
```

## バックアップ

### データベースバックアップ

```bash
# バックアップ作成
docker-compose -f docker-compose.prod.yml exec postgres \
  pg_dump -U oneco oneco > backup_$(date +%Y%m%d).sql

# バックアップからリストア
docker-compose -f docker-compose.prod.yml exec -T postgres \
  psql -U oneco oneco < backup_20260210.sql
```

### スナップショットバックアップ

```bash
# スナップショットファイルをバックアップ
cp snapshots/latest.json backups/snapshot_$(date +%Y%m%d).json
```

## トラブルシューティング

### API が起動しない

```bash
# ログを確認
docker-compose -f docker-compose.prod.yml logs api

# データベース接続を確認
docker-compose -f docker-compose.prod.yml exec postgres \
  pg_isready -U oneco
```

### マイグレーションエラー

```bash
# 現在のマイグレーションバージョンを確認
docker-compose -f docker-compose.prod.yml run --rm migration alembic current

# マイグレーション履歴を確認
docker-compose -f docker-compose.prod.yml run --rm migration alembic history
```

### パフォーマンス問題

```bash
# コネクションプールサイズを調整
# .env.production で設定
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=40

# Redis メモリ使用量を確認
docker-compose -f docker-compose.prod.yml exec redis redis-cli INFO memory
```

## スケーリング

### 水平スケーリング

```bash
# API サーバーを3台にスケール
docker-compose -f docker-compose.prod.yml up -d --scale api=3

# ロードバランサー（Nginx/Traefik）を追加
```

### 垂直スケーリング

```bash
# リソース制限を設定
# docker-compose.prod.yml に追加
services:
  api:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
```

## セキュリティ

### SSL/TLS設定

- Let's Encrypt で証明書を取得
- Nginx/Traefik でリバースプロキシ設定
- HTTPS 強制リダイレクト

### ファイアウォール設定

```bash
# 必要なポートのみ開放
ufw allow 80/tcp   # HTTP
ufw allow 443/tcp  # HTTPS
ufw allow 22/tcp   # SSH
ufw enable
```

### 定期的なセキュリティアップデート

```bash
# Docker イメージを最新化
docker-compose -f docker-compose.prod.yml pull
docker-compose -f docker-compose.prod.yml up -d
```

## サポート

問題が発生した場合:
1. ログを確認（`docker-compose logs`）
2. ヘルスチェックを実行（`/health` エンドポイント）
3. GitHub Issues で報告
