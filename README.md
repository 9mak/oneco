# oneco - 保護動物情報管理システム

保護動物情報を自動収集し、データベースで管理、REST API経由で提供、LINE通知を配信する統合システム

## 🎯 概要

**oneco**は、自治体の保護動物情報を自動収集・正規化し、データベースで一元管理、公開Webポータルで閲覧可能にし、LINE通知で新着情報を配信する包括的なシステムです。

### 主要機能

- 🤖 **自動データ収集**: 自治体サイトから保護動物情報を毎日自動収集
- 💾 **データベース管理**: PostgreSQLで動物データを永続化・管理
- 🔍 **REST API**: 外部システムがデータを取得できるAPI提供
- 📰 **RSS/Atom配信**: 保護動物情報をフィード形式で配信
- 📱 **LINE通知**: ユーザーの条件に合致する動物を自動通知
- 🌐 **公開Webポータル**: 一般ユーザーが保護動物情報を検索・閲覧

## 🏗️ アーキテクチャ

```
┌─────────────────┐
│ 自治体サイト    │
│ (高知県等)      │
└────────┬────────┘
         │ スクレイピング
         ▼
┌─────────────────┐      ┌──────────────┐
│ data-collector  │─────▶│ PostgreSQL   │
│ (Python)        │      │ Database     │
└─────────────────┘      └──────┬───────┘
         │                       │
         │ 新着通知              │ データ取得
         ▼                       ▼
┌─────────────────┐      ┌──────────────┐
│ notification-   │      │ REST API     │
│ manager         │      │ (FastAPI)    │
│ (LINE Bot)      │      └──────┬───────┘
└─────────────────┘             │
         │                      │ データ配信
         │ LINE配信             ▼
         ▼              ┌──────────────┐
┌─────────────────┐    │ Webポータル  │
│ LINE Users      │    │ (Next.js)    │
└─────────────────┘    └──────────────┘
```

## 🚀 クイックスタート

### 前提条件

- Python 3.11+
- Node.js 20+
- Docker & Docker Compose
- PostgreSQL 15+
- Redis 7+

### 開発環境セットアップ

```bash
# リポジトリをクローン
git clone https://github.com/your-org/oneco.git
cd oneco

# 環境変数を設定
cp .env.example .env
# .env を編集して必要な値を設定

# Docker サービスを起動（PostgreSQL + Redis）
docker-compose up -d

# Python バックエンドをセットアップ
pip install -r requirements.txt
pip install -e .

# データベースマイグレーションを実行
alembic upgrade head

# API サーバーを起動
uvicorn data_collector.infrastructure.api.app:app --reload

# フロントエンドをセットアップ（別ターミナル）
cd frontend
npm install
npm run dev
```

### サービス起動確認

- API: http://localhost:8000
- API ドキュメント: http://localhost:8000/docs
- フロントエンド: http://localhost:3000
- PostgreSQL: localhost:5432
- Redis: localhost:6379

## 📦 プロジェクト構成

```
oneco/
├── src/
│   ├── data_collector/        # データ収集エンジン
│   │   ├── adapters/          # 自治体サイトアダプター
│   │   ├── domain/            # ドメインモデル・ロジック
│   │   ├── infrastructure/    # インフラ層（DB, API）
│   │   └── orchestration/     # 収集オーケストレーション
│   ├── notification_manager/  # LINE通知管理
│   └── syndication_service/   # RSS/Atom配信
├── frontend/                  # Next.js Webポータル
├── tests/                     # テストコード
├── alembic/                   # データベースマイグレーション
├── .github/workflows/         # CI/CD設定
├── docker-compose.yml         # 開発環境Docker構成
├── docker-compose.prod.yml    # 本番環境Docker構成
└── Dockerfile                 # Backend API Dockerfile
```

## 🧪 テスト

```bash
# 全テスト実行
pytest

# カバレッジ付きテスト
pytest --cov=src/data_collector --cov-report=html

# 特定のテストのみ実行
pytest tests/test_animal_repository.py -v

# フロントエンドテスト
cd frontend
npm test
npm run test:coverage
```

### テスト統計

| コンポーネント | テスト数 | 状態 |
|--------------|---------|------|
| animal-api-persistence | 110 | ✅ 100% |
| data-collector | 178 | ✅ 100% |
| notification-manager | 192 | ✅ 100% |
| syndication-service | 61 | ✅ 100% |
| public-web-portal | 74 | ✅ 100% |
| **合計** | **615+** | **✅ 100%** |

## 🚢 本番デプロイ

詳細は [DEPLOYMENT.md](./DEPLOYMENT.md) を参照してください。

### クイック本番デプロイ

```bash
# 環境変数を設定
cp .env.production.example .env.production
vim .env.production

# Docker Compose で起動
docker-compose -f docker-compose.prod.yml up -d

# マイグレーション実行
docker-compose -f docker-compose.prod.yml run --rm migration

# ヘルスチェック
curl http://localhost:8000/health
```

## 📚 ドキュメント

- [API ドキュメント](http://localhost:8000/docs) - FastAPI自動生成
- [デプロイガイド](./DEPLOYMENT.md) - 本番環境構築手順
- [フロントエンド README](./frontend/README.md) - Next.jsアプリケーション
- [Kiro 仕様](./.kiro/specs/) - 各機能の詳細仕様

## 🔧 開発ガイドライン

### コードスタイル

```bash
# Python Linting
ruff check src/ tests/

# Python Formatting
ruff format src/ tests/

# TypeScript Linting
cd frontend
npm run lint
```

### Git コミット

```bash
# Conventional Commits形式を推奨
git commit -m "feat: 新機能追加"
git commit -m "fix: バグ修正"
git commit -m "docs: ドキュメント更新"
```

### CI/CD

- **Backend**: `.github/workflows/backend.yml`
  - Lint → Test → Build → Deploy
- **Frontend**: `.github/workflows/frontend.yml`
  - Lint → Test → Build → Vercel Deploy
- **Data Collector**: `.github/workflows/data-collector.yml`
  - 毎日 JST 00:00 自動実行

## 🤝 コントリビューション

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'feat: Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 ライセンス

MIT License - 詳細は [LICENSE](./LICENSE) を参照

## 🙏 謝辞

- 高知県動物愛護センター
- Claude Code (Anthropic)
- Kiro AI-DLC フレームワーク

## 📞 サポート

- GitHub Issues: https://github.com/your-org/oneco/issues
- Email: admin@example.com

---

🐕 🐈 保護動物に新しい家族を
