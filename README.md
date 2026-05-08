# oneco - 保護動物情報管理システム

保護動物情報を自動収集し、データベースで管理、REST API 経由で提供する統合システム

## 概要

**oneco** は、自治体の保護動物情報を自動収集・正規化し、データベースで一元管理、公開 Web ポータルで閲覧可能にするシステムです。

### 主要機能

- **自動データ収集**: 自治体サイトから保護動物情報を毎日自動収集（GitHub Actions）
- **LLM 解析**: Anthropic Claude / Groq で各自治体の不定形な HTML・PDF を解析
- **REST API**: FastAPI による動物データ API（フィルタ・ページング対応）
- **Web ポータル**: Next.js による保護動物の検索・閲覧画面

## アーキテクチャ

```
自治体サイト
     │ LLM スクレイピング (Anthropic Claude / Groq)
     ▼
GitHub Actions ──▶ Supabase PostgreSQL
(data-collector)          │
                          │ REST API
                          ▼
                   Google Cloud Run
                   (FastAPI backend)
                          │
                          │ データ取得
                          ▼
                      Vercel
                   (Next.js frontend)
```

### 本番環境

| コンポーネント | サービス | URL |
|-------------|---------|-----|
| Backend API | Google Cloud Run (`asia-northeast1`) | `https://oneco-api-tvlsrcvyuq-an.a.run.app` |
| Frontend | Vercel | GitHub push で自動デプロイ |
| Database | Supabase PostgreSQL | aws-1-ap-northeast-2 |
| Data Collector | GitHub Actions | 毎日 JST 00:00 自動実行 |

## プロジェクト構成

```
oneco/
├── src/
│   ├── data_collector/        # データ収集エンジン（Python）
│   │   ├── domain/            # ドメインモデル・バリデーション
│   │   ├── infrastructure/    # DB, API, LLM アダプター
│   │   └── orchestration/     # 収集オーケストレーション
│   ├── notification_manager/  # LINE 通知管理
│   └── syndication_service/   # RSS/Atom 配信
├── frontend/                  # Next.js Web ポータル
├── tests/                     # テストコード
├── alembic/                   # データベースマイグレーション
├── .github/workflows/         # CI/CD
│   ├── backend.yml            # Backend テスト
│   ├── frontend.yml           # Frontend テスト + Vercel デプロイ
│   └── data-collector.yml     # 毎日データ収集
├── Dockerfile                 # Cloud Run 用イメージ
└── run_server.py              # uvicorn エントリポイント
```

## ローカル開発

### 前提条件

- Python 3.11+
- Node.js 20+

### セットアップ

```bash
# リポジトリをクローン
git clone https://github.com/9mak/oneco.git
cd oneco

# Python 依存関係インストール
pip install -e ".[dev]"

# 環境変数を設定（.env.example を参考に）
cp .env.example .env

# データベースマイグレーション
alembic upgrade head

# API サーバー起動
uvicorn run_server:app --reload

# フロントエンド起動（別ターミナル）
cd frontend && npm install && npm run dev
```

| サービス | URL |
|---------|-----|
| API | http://localhost:8000 |
| API docs | http://localhost:8000/docs |
| Frontend | http://localhost:3000 |

## テスト

```bash
# バックエンド全テスト
pytest

# カバレッジ付き
pytest --cov=src --cov-report=html

# フロントエンドテスト
cd frontend && npm test
```

## 本番デプロイ

詳細は [DEPLOYMENT.md](./DEPLOYMENT.md) を参照。

### 環境変数（Backend）

| 変数名 | 説明 | 必須 |
|--------|------|------|
| `DATABASE_URL` | Supabase PostgreSQL 接続 URL (`postgresql+asyncpg://...`) | ✅ |
| `CORS_ORIGINS` | 許可する CORS オリジン（`*` または フロントエンド URL） | ✅ |
| `LOG_LEVEL` | ログレベル（`INFO` / `DEBUG`） | - |

### 環境変数（Data Collector）

| 変数名 | 説明 | 必須 |
|--------|------|------|
| `DATABASE_URL` | Supabase PostgreSQL 接続 URL | ✅ |
| `GROQ_API_KEY` | Groq API キー（デフォルトプロバイダー） | ✅ |
| `ANTHROPIC_API_KEY` | Claude API キー（オーバーライド指定時） | - |
| `INTERNAL_API_TOKEN` | 内部 API（PATCH/admin）認証トークン | ✅ |
| `SLACK_WEBHOOK_URL` | 収集結果通知用 Slack Webhook | - |
| `AUTH_SECRET` | NextAuth セッション暗号化キー | ✅ (frontend) |
| `AUTH_GITHUB_ID` / `AUTH_GITHUB_SECRET` | GitHub OAuth App | ✅ (frontend) |
| `ADMIN_GITHUB_LOGIN` | /admin に許可する GitHub username | ✅ (frontend) |

## CI/CD

| ワークフロー | トリガー | 内容 |
|------------|---------|------|
| `backend.yml` | push / PR → main | Lint → Test → Build |
| `frontend.yml` | push / PR → main | Lint → Test → Vercel デプロイ |
| `data-collector.yml` | 毎日 JST 00:00 | 自治体サイトからデータ収集 |

## ライセンス

[MIT License](LICENSE)

## コントリビュート

[CONTRIBUTING.md](CONTRIBUTING.md) を参照してください。
セキュリティ問題は [SECURITY.md](SECURITY.md) の連絡先まで非公開で報告してください。

---

🐕 🐈 保護動物に新しい家族を
