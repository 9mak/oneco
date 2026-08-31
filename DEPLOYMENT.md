# 本番環境デプロイガイド

実際の本番環境は **Google Cloud Run + Vercel + Supabase** 構成です。

## 構成概要

| コンポーネント | サービス | リージョン |
|-------------|---------|---------|
| Backend API | Google Cloud Run | `asia-northeast1`（東京） |
| Container Registry | Artifact Registry | `asia-northeast1` |
| Database | Supabase PostgreSQL | `aws-1-ap-northeast-2` |
| Frontend | Vercel | 自動（CDN） |
| Data Collector | Google Cloud Run Jobs（`oneco-collector`。Cloud Scheduler 0:00 JST 起動） | `asia-northeast1` |

---

## Backend デプロイ（Cloud Run）

### 前提条件

- `gcloud` CLI インストール・認証済み
- GCP プロジェクト設定済み
- Artifact Registry リポジトリ作成済み

### 手順

```bash
# 1. Docker イメージをビルドして Artifact Registry にプッシュ
PROJECT_ID="your-gcp-project-id"
REGION="asia-northeast1"
IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/oneco/oneco-api"

gcloud builds submit --tag $IMAGE .

# 2. Cloud Run にデプロイ
gcloud run deploy oneco-api \
  --image $IMAGE \
  --region $REGION \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars DATABASE_URL="postgresql+asyncpg://...",CORS_ORIGINS="*",LOG_LEVEL="INFO"
```

### 環境変数

Cloud Run の環境変数として設定する：

| 変数名 | 説明 | 例 |
|--------|------|---|
| `DATABASE_URL` | Supabase 接続 URL（**transaction-mode プーラー :6543**。session mode :5432 は EMAXCONNSESSION で枯渇した経緯があり使わない。PR #233） | `postgresql+asyncpg://postgres.<project>:<pass>@aws-1-ap-northeast-2.pooler.supabase.com:6543/postgres` |
| `CORS_ORIGINS` | 許可 CORS オリジン（カンマ区切り、本番ドメイン明示推奨） | `https://your-frontend.vercel.app` |
| `LOG_LEVEL` | ログレベル | `INFO` |
| `INTERNAL_API_TOKEN` | **必須**: PATCH /animals/{id}/status 等の内部 API 認証トークン。`openssl rand -hex 32` で生成し Secret Manager 推奨 | `<32-byte hex>` |

### ヘルスチェック

```bash
curl https://oneco-api-tvlsrcvyuq-an.a.run.app/health
# {"status":"healthy","timestamp":"..."}
```

### データベースマイグレーション

`deploy-backend.yml` が push デプロイ時に `alembic upgrade head` を自動適用する。ローカルから手動で実行する場合：

```bash
# ローカルから Supabase に対して実行
DATABASE_URL="postgresql+asyncpg://..." alembic upgrade head
```

---

## Frontend デプロイ（Vercel）

### 自動デプロイ

`main` ブランチへの push で Vercel が自動デプロイします。GitHub Actions の `frontend.yml` がテストを通過後、Vercel の GitHub 連携が発火します。

### 手動デプロイ（初期設定・緊急時）

```bash
cd frontend
npm install -g vercel
vercel --prod
```

### 環境変数（Vercel ダッシュボードで設定）

| 変数名 | 説明 |
|--------|------|
| `NEXT_PUBLIC_API_BASE_URL` | Backend API のベース URL（例: `https://oneco-api-tvlsrcvyuq-an.a.run.app`） |
| `NEXT_PUBLIC_SITE_URL` | 本番サイトの URL（canonical / sitemap / OGP に使用。未設定だと本番ビルドが失敗するガードあり） |

---

## Database（Supabase）

### マイグレーション適用

```bash
# alembic で直接 Supabase に適用
DATABASE_URL="postgresql+asyncpg://<接続文字列>" alembic upgrade head

# 適用済みバージョン確認
DATABASE_URL="postgresql+asyncpg://<接続文字列>" alembic current
```

### 接続確認

Supabase ダッシュボード → Table Editor → `animals` テーブルでデータを確認。

---

## Data Collector（GCP Cloud Run Jobs）

### 自動実行

毎日 JST 00:00 に Cloud Scheduler が Cloud Run Jobs `oneco-collector`（`asia-northeast1`）を起動します。実行内容は `scripts/collector_entrypoint.sh`（`9mak/oneco` を認証なし HTTPS で shallow clone → `alembic upgrade head` → `9mak/oneco-state`（状態ファイル専用の private リポジトリ、deploy key 認証）から前回状態を復元 → `python -m data_collector` → 状態ファイルを `9mak/oneco-state` へ commit&push）。9mak/oneco 自体への書き込みは行いません（T112: deploy key の権限範囲をアプリ本体から状態ファイル専用リポジトリへ縮小）。

`.github/workflows/data-collector.yml`（GitHub Actions 版）は GCP 側が使えないときの手動フォールバックとしてのみ残しています（`workflow_dispatch` のみ、定期実行はしません）。

### デプロイ

`src/**`・`Dockerfile.collector`・`cloudbuild-collector.yaml`・`scripts/collector_entrypoint.sh` 等を `main` に push すると `.github/workflows/deploy-collector.yml` が自動でイメージを再ビルドし、`gcloud run jobs update` で Cloud Run Job の image / 環境変数を宣言的に更新します（WIF キーレス認証、`deploy-backend.yml` と同じ仕組み）。ジョブ構成（timeout・CPU・メモリ等）はこのステップに完全宣言されており、GCP コンソール側での手変更は次回デプロイで上書きされます。実行スケジュール自体（Cloud Scheduler）はこのワークフローの対象外です。

### 手動実行

```bash
# GCP 側を直接実行
gcloud run jobs execute oneco-collector --region asia-northeast1 --project oneco-app

# GCP が使えない場合の代替経路（GitHub Actions フォールバック、workflow_dispatch 権限が必要）
gh workflow run "Data Collector" --ref main
```

障害対応の詳細手順（実行履歴・ログの見方等）は [docs/RUNBOOK.md#c-収集の異常](docs/RUNBOOK.md#c-収集の異常) 参照。

### 必要な Secrets

Cloud Run Job（`oneco-collector`）本体は GCP Secret Manager の Secret（`DATABASE_URL` / `GROQ_API_KEY` / `DISCORD_WEBHOOK_URL` / `GIT_STATE_DEPLOY_KEY`）を参照します（`sync-collector-secrets.yml` で GitHub Secrets から複製されるのは `DATABASE_URL` / `GROQ_API_KEY` / `DISCORD_WEBHOOK_URL` のみ。`GIT_STATE_DEPLOY_KEY` は `gcloud secrets` で直接登録する）。

> `GIT_STATE_DEPLOY_KEY`（旧 `GIT_DEPLOY_KEY`, T112 で改称）: `9mak/oneco-state`（状態ファイル 5 点専用の private リポジトリ）への読み書き専用 deploy key。9mak/oneco 本体への書き込み権限は持たない。9mak/oneco 自体は public repo のため、collector の `alembic upgrade head` 用ソース取得は認証なし HTTPS clone で行う。

以下の GitHub Secrets は、GitHub Actions 側で動くワークフロー（collector のフォールバック実行 `data-collector.yml` に加え、`sns-publish.yml` / `secret-health.yml` 等）が使うものです：

| Secret 名 | 説明 | 必須 |
|-----------|------|------|
| `DATABASE_URL` | Supabase PostgreSQL 接続 URL | ✅ |
| `GROQ_API_KEY` | Groq API キー（デフォルト LLM プロバイダ。抽出セレクタ生成等に使用） | ✅ |
| `ANTHROPIC_API_KEY` | Claude API キー。secrets 定義はあるが **実装未着手**（`src` 内に参照コードなし。`PROVIDER_REGISTRY` は現状 Groq のみ、`src/data_collector/__main__.py:50` 付近のコメント参照）。設定しても収集の挙動は変わらない | - |
| `SLACK_WEBHOOK_URL` | 運用アラート通知用 Slack Incoming Webhook（収集失敗 / 連続失敗サイト / フィールド品質ドリフト / 件数ゼロ回帰） | - |
| `DISCORD_WEBHOOK_URL` | 運用アラート通知用 Discord Webhook（Slack と同内容・併用可。どちらか設定すれば発火） | - |
| `THREADS_ACCESS_TOKEN` | Threads Graph API の long-lived access token。`sns-publish.yml` で使用。未設定だと SNS publisher は `no_api_client` で停止 | - |
| `THREADS_USER_ID` | Threads アカウントの数値 ID。`me?fields=id` で取得 | - |

> 監視アラートは `SLACK_WEBHOOK_URL` / `DISCORD_WEBHOOK_URL` のどちらか（または両方）を設定した時点で発火する。未設定なら no-op（収集自体は継続）。
> Discord Webhook の作り方: 対象サーバー → チャンネルの「編集」→「連携サービス」→「ウェブフック」→「新しいウェブフック」→ URL をコピー。
> ゼロ件回帰の連続閾値は `ONECO_ZERO_DROP_THRESHOLD`（既定 2）で調整可能。
> GCP 実行（`oneco-collector`）には `DISCORD_WEBHOOK_URL` のみ複製されている（`SLACK_WEBHOOK_URL` は Secret Manager 未登録）。Slack 通知は GitHub Actions フォールバック実行時のみ発火する。

### SNS Publisher (Threads) repo variables

GitHub リポジトリの Settings → Secrets and variables → Actions → **Variables** tab で設定：

| 変数名 | 既定 | 説明 |
|--------|------|------|
| `THREADS_PUBLISH_ENABLED` | `false` | `true` にしない限り `sns-publish.yml` は一切投稿しない (kill switch) |
| `THREADS_PUBLISH_DRY_RUN` | `true` | `true` なら moderate まで通すが Threads には POST しない (post_log にのみ記録) |

段階リリース手順:
1. `THREADS_ACCESS_TOKEN` / `THREADS_USER_ID` を secrets に登録
2. `THREADS_PUBLISH_ENABLED=true` のみ設定 (dry_run は既定 true のまま) → 数日 post_log を観察
3. 投稿候補に問題ないことを確認したら **`data/sns_posts.yaml` を空にして** から `THREADS_PUBLISH_DRY_RUN=false` に切替
   - ⚠️ post_log は dry_run 期間の URL も記録しているため、空にしないと「既に投稿済」と誤認されて全件スキップになる

### 収集失敗の対処

1. **Groq レート制限/クォータ超過**: 時間をおいて再実行で解消（`ANTHROPIC_API_KEY` によるフォールバックは前述の通り未実装のため使えない）。
2. **ネットワークタイムアウト**: 外部自治体サイトの問題。数日中に自動回復。
3. **DB 保存失敗**: Cloud Run Jobs のログ（フォールバック実行時は GitHub Actions のログ）で `Failed to save animal to database:` の後のエラー内容を確認。

詳しい障害対応手順（実行履歴の見方・手動再実行等）は [docs/RUNBOOK.md#c-収集の異常](docs/RUNBOOK.md#c-収集の異常) 参照。

---

## CI/CD パイプライン

```
git push → GitHub Actions
               │
               ├─ backend.yml          ─▶ Lint → Test → Build
               ├─ deploy-backend.yml   ─▶ alembic → Cloud Build → Cloud Run デプロイ（自動）
               ├─ frontend.yml         ─▶ Lint → Test → Vercel デプロイ（自動）
               └─ deploy-collector.yml ─▶ Cloud Build → Cloud Run Jobs (oneco-collector) 更新（自動）

Cloud Scheduler (0:00 JST) ─▶ Cloud Run Jobs (oneco-collector) ─▶ データ収集
  ※ data-collector.yml（GitHub Actions）は GCP 障害時の手動フォールバックのみ。定期実行はしない
```

Backend（Cloud Run）は `deploy-backend.yml` により `main` への push で自動デプロイされる（`src/`・`Dockerfile`・`requirements.txt`・`pyproject.toml`・`alembic/` 変更時）。WIF でキーレス認証し、push 時は `alembic upgrade head` も自動適用される。手動デプロイは `workflow_dispatch`（`run_migration` トグルあり）または上記の `gcloud run deploy` で可能。

Data Collector（Cloud Run Jobs）は `deploy-collector.yml` により同じく `main` への push で自動デプロイされる（`src/`・`Dockerfile.collector`・`cloudbuild-collector.yaml`・`scripts/collector_entrypoint.sh` 変更時）。同じ WIF 認証を使うがデプロイのみで、実行スケジュール（Cloud Scheduler）はこのワークフローの対象外。

---

## ロールバック

### Backend（Cloud Run）

```bash
# 前リビジョンに 100% トラフィックを戻す
gcloud run services update-traffic oneco-api \
  --region asia-northeast1 \
  --to-revisions oneco-api-00004-j9g=100
```

### Frontend（Vercel）

Vercel ダッシュボード → Deployments → 旧デプロイの「Promote to Production」

---

## 監視・確認

```bash
# Cloud Run ステータス
gcloud run services describe oneco-api --region asia-northeast1

# 最新リビジョン一覧
gcloud run revisions list --service oneco-api --region asia-northeast1

# GitHub Actions 直近の実行
gh run list --limit 10

# API ヘルスチェック
curl https://oneco-api-tvlsrcvyuq-an.a.run.app/health
```
