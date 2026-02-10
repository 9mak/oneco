# 本番環境デプロイチェックリスト

このチェックリストは、本番環境へのデプロイ前に確認すべき項目を網羅しています。

## 📋 デプロイ前チェック

### 1. インフラストラクチャ準備

- [ ] **クラウドプロバイダー選定**
  - AWS / GCP / Azure / その他
  - リージョン選定

- [ ] **PostgreSQL データベース**
  - [ ] マネージドサービス契約 (RDS / Cloud SQL / Azure Database)
  - [ ] インスタンスタイプ選定 (最小: 2GB RAM)
  - [ ] バックアップ自動化設定
  - [ ] 暗号化有効化
  - [ ] 接続情報の記録

- [ ] **Redis キャッシュ**
  - [ ] マネージドサービス契約 (ElastiCache / Memorystore)
  - [ ] インスタンスタイプ選定 (最小: 256MB)
  - [ ] 永続化設定 (AOF または RDB)
  - [ ] 接続情報の記録

- [ ] **コンテナホスティング**
  - [ ] サービス選定 (ECS / Cloud Run / App Service)
  - [ ] コンテナレジストリ設定 (ECR / GCR / ACR)
  - [ ] リソース割り当て (CPU: 1, Memory: 2GB)
  - [ ] オートスケーリング設定

- [ ] **ドメイン & SSL**
  - [ ] ドメイン取得
  - [ ] DNS設定
  - [ ] SSL証明書取得 (Let's Encrypt推奨)
  - [ ] HTTPS設定

### 2. 環境変数設定

- [ ] **.env.production 作成**
  ```bash
  cp .env.production.example .env.production
  ```

- [ ] **必須環境変数の設定**
  - [ ] `POSTGRES_PASSWORD`: 強力なパスワード (16文字以上)
  - [ ] `DATABASE_URL`: 本番PostgreSQL接続文字列
  - [ ] `REDIS_URL`: 本番Redis接続文字列
  - [ ] `SECRET_KEY`: ランダムな秘密鍵生成
  - [ ] `CORS_ORIGINS`: フロントエンドドメイン設定
  - [ ] `LINE_CHANNEL_ACCESS_TOKEN`: LINE Messaging APIトークン
  - [ ] `LINE_CHANNEL_SECRET`: LINEチャネルシークレット
  - [ ] `NOTIFICATION_EMAIL`: 運用者メールアドレス
  - [ ] `SLACK_WEBHOOK_URL`: Slack通知用Webhook URL

- [ ] **GitHub Secrets設定**
  - Settings > Secrets and variables > Actions で設定
  - [ ] `DATABASE_URL`
  - [ ] `NOTIFICATION_EMAIL`
  - [ ] `SLACK_WEBHOOK_URL`

### 3. セキュリティ設定

- [ ] **ファイアウォール**
  - [ ] HTTP (80) 開放
  - [ ] HTTPS (443) 開放
  - [ ] SSH (22) 必要に応じて開放
  - [ ] PostgreSQL (5432) 内部ネットワークのみ
  - [ ] Redis (6379) 内部ネットワークのみ

- [ ] **アクセス制御**
  - [ ] データベースユーザー権限の最小化
  - [ ] API認証設定 (将来実装)
  - [ ] CORS設定の確認

- [ ] **シークレット管理**
  - [ ] 環境変数をGitにコミットしない
  - [ ] `.env.production` を `.gitignore` に追加済み確認
  - [ ] パスワードマネージャーでシークレット管理

### 4. データベース準備

- [ ] **マイグレーション**
  ```bash
  alembic upgrade head
  ```

- [ ] **初期データ投入** (必要に応じて)
  ```bash
  python scripts/seed_data.py
  ```

- [ ] **インデックス確認**
  - [ ] animals テーブルのインデックス作成確認
  - [ ] パフォーマンステスト実施

### 5. Docker イメージ準備

- [ ] **イメージビルド**
  ```bash
  docker build -t oneco-api:latest .
  ```

- [ ] **イメージテスト**
  ```bash
  docker run --rm oneco-api:latest python -c "import data_collector; print('OK')"
  ```

- [ ] **レジストリプッシュ** (本番環境の場合)
  ```bash
  docker tag oneco-api:latest your-registry/oneco-api:v1.0.0
  docker push your-registry/oneco-api:v1.0.0
  ```

### 6. デプロイ実行

- [ ] **デプロイスクリプト実行**
  ```bash
  ./scripts/deployment/deploy.sh production
  ```

- [ ] **サービス起動確認**
  ```bash
  docker-compose -f docker-compose.prod.yml ps
  ```

### 7. 動作確認

- [ ] **ヘルスチェック**
  ```bash
  curl https://your-domain.com/health
  ```

- [ ] **API動作確認**
  ```bash
  curl https://your-domain.com/animals?limit=10
  ```

- [ ] **OpenAPI ドキュメント確認**
  - https://your-domain.com/docs

- [ ] **RSS/Atom フィード確認**
  ```bash
  curl https://your-domain.com/feeds/rss
  ```

- [ ] **データベース接続確認**
  ```bash
  docker-compose -f docker-compose.prod.yml exec postgres psql -U oneco -c "SELECT count(*) FROM animals;"
  ```

### 8. モニタリング設定

- [ ] **ヘルスチェック監視**
  - [ ] Cron ジョブで定期ヘルスチェック
  ```bash
  */5 * * * * /path/to/scripts/monitoring/health_check.sh
  ```

- [ ] **ログ監視**
  - [ ] CloudWatch / Stackdriver / Azure Monitor 設定
  - [ ] エラーアラート設定

- [ ] **メトリクス収集**
  - [ ] Prometheus / Datadog / New Relic 設定 (オプション)

- [ ] **アラート設定**
  - [ ] ダウンタイムアラート
  - [ ] エラー率アラート
  - [ ] ディスク使用量アラート

### 9. バックアップ設定

- [ ] **自動バックアップ**
  - [ ] Cron ジョブで毎日バックアップ
  ```bash
  0 2 * * * /path/to/scripts/backup/backup.sh
  ```

- [ ] **バックアップ保管場所**
  - [ ] S3 / Cloud Storage / Azure Blob へアップロード
  - [ ] 保持期間設定 (推奨: 30日)

- [ ] **リストアテスト**
  ```bash
  ./scripts/backup/restore.sh backups/backup_YYYYMMDD_HHMMSS.tar.gz
  ```

### 10. パフォーマンステスト

- [ ] **負荷テスト**
  - [ ] 同時100リクエスト処理確認
  - [ ] レスポンスタイム < 500ms 確認

- [ ] **キャッシュ効率確認**
  - [ ] Redis ヒット率 > 70% 確認

- [ ] **データベースパフォーマンス**
  - [ ] スロークエリログ確認
  - [ ] インデックス使用確認

## 📊 デプロイ後チェック

### 即時確認 (デプロイ後30分以内)

- [ ] **サービス稼働確認**
  ```bash
  ./scripts/monitoring/health_check.sh --verbose
  ```

- [ ] **ログ確認**
  ```bash
  docker-compose -f docker-compose.prod.yml logs -f api
  ```

- [ ] **エラー監視**
  - [ ] エラーログがないことを確認
  - [ ] 予期しない動作がないことを確認

### 1日後確認

- [ ] **データ収集確認**
  - [ ] data-collector が正常に実行されたか
  - [ ] GitHub Actions ワークフローの成功確認

- [ ] **通知配信確認**
  - [ ] LINE通知が正常に配信されたか
  - [ ] notification-manager ログ確認

- [ ] **バックアップ確認**
  - [ ] 自動バックアップが実行されたか
  - [ ] バックアップファイルの整合性確認

### 1週間後確認

- [ ] **パフォーマンス分析**
  - [ ] レスポンスタイム推移
  - [ ] エラー率推移
  - [ ] リソース使用率推移

- [ ] **ディスク使用量確認**
  - [ ] データベース容量
  - [ ] ログファイル容量
  - [ ] バックアップ容量

- [ ] **ユーザーフィードバック収集**
  - [ ] 動作不具合報告の確認
  - [ ] パフォーマンス問題の確認

## 🚨 トラブルシューティング

### サービスが起動しない

1. ログを確認
   ```bash
   docker-compose -f docker-compose.prod.yml logs api
   ```

2. 環境変数を確認
   ```bash
   docker-compose -f docker-compose.prod.yml config
   ```

3. データベース接続を確認
   ```bash
   docker-compose -f docker-compose.prod.yml exec postgres pg_isready -U oneco
   ```

### パフォーマンスが悪い

1. リソース使用状況を確認
   ```bash
   docker stats
   ```

2. スロークエリを確認
   ```sql
   SELECT * FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 10;
   ```

3. コネクションプールを調整
   - `DB_POOL_SIZE` を増加
   - `DB_MAX_OVERFLOW` を調整

### データベースエラー

1. マイグレーション状態を確認
   ```bash
   alembic current
   alembic history
   ```

2. データベース整合性を確認
   ```sql
   VACUUM ANALYZE;
   REINDEX DATABASE oneco;
   ```

## 📞 緊急連絡先

- インフラ管理者: [連絡先]
- データベース管理者: [連絡先]
- 開発チームリーダー: [連絡先]

## 📚 参考資料

- [DEPLOYMENT.md](./DEPLOYMENT.md) - デプロイガイド
- [README.md](./README.md) - プロジェクト概要
- [API Documentation](https://your-domain.com/docs) - API仕様

---

**最終更新**: 2026-02-10
**次回レビュー**: デプロイ後1週間
