# ギャップ分析: public-web-portal

## 1. 現状調査

### 1.1 既存アセット

#### バックエンド API
- **ファイル**: `src/data_collector/infrastructure/api/routes.py`
- **エンドポイント**:
  - `GET /animals`: 動物一覧取得（フィルタリング、ページネーション対応）
  - `GET /animals/{animal_id}`: 動物詳細取得
  - `GET /health`: ヘルスチェック
- **スキーマ**: `src/data_collector/infrastructure/api/schemas.py`
  - `AnimalPublic`: 公開用動物データスキーマ（`id`, `species`, `sex`, `age_months`, `color`, `size`, `shelter_date`, `location`, `phone`, `image_urls`, `source_url`, `category`）
  - `PaginatedResponse[T]`: ジェネリック型のページネーション付きレスポンス
  - `PaginationMeta`: ページネーションメタデータ

#### データベース層
- **ファイル**: `src/data_collector/infrastructure/database/models.py`
- **テーブル**: `Animal` - 全フィールドに対応したインデックス付き
- **リポジトリ**: `src/data_collector/infrastructure/database/repository.py`
  - `list_animals_orm()`: フィルタリング・ページネーション機能
  - カテゴリフィルタ（`adoption`, `lost`）対応済み

#### FastAPI アプリケーション
- **ファイル**: `src/data_collector/infrastructure/api/app.py`
- **特徴**:
  - CORS設定（`CORS_ORIGINS` 環境変数で制御）
  - ライフサイクル管理（データベース接続の初期化・クローズ）
  - グローバルな `DatabaseConnection` インスタンス

#### 技術スタック
- **バックエンド**: Python 3.11+, FastAPI, SQLAlchemy 2.0, Pydantic
- **データベース**: PostgreSQL (本番), SQLite (テスト)
- **テスト**: pytest, pytest-asyncio, pytest-cov, httpx
- **デプロイ**: uvicorn

### 1.2 アーキテクチャパターン
- **レイヤードアーキテクチャ**: domain, infrastructure, orchestration の明確な分離
- **依存性注入**: コンストラクタベース
- **型安全性**: Pydantic によるバリデーション
- **構造化ロギング**: Python `logging` モジュール
- **テスト配置**: `tests/` ディレクトリに対応する構造（`tests/infrastructure/`, `tests/domain/` など）

### 1.3 統合サーフェス
- **CORS**: すでに設定済み（`allow_origins`, `allow_credentials`, `allow_methods`, `allow_headers`）
- **API仕様**: OpenAPI / Swagger 自動生成（FastAPI標準機能）
- **データ形式**: JSON（ISO 8601形式の日付）
- **フィルタパラメータ**: `species`, `sex`, `location`, `category`, `shelter_date_from`, `shelter_date_to`, `limit`, `offset`

### 1.4 既存の制約
- **パッケージ構成**: 現在は `data-collector` という単一パッケージ（モノリポ構成）
- **フロントエンドの不在**: Web UIは存在せず、バックエンドAPIのみ実装済み
- **デプロイ分離**: フロントエンドとバックエンドの分離デプロイが必要（将来的にVercel/Netlifyなどの静的ホスティングとバックエンドAPIを分ける可能性）
- **認証・認可**: 現在未実装（Phase 2で検討予定、public-web-portalは公開Webポータルのため認証不要）

---

## 2. 要件実現性分析

### 2.1 要件とアセットのマッピング

| 要件 | 必要な技術要素 | ギャップ状態 | 詳細 |
|------|----------------|-------------|------|
| **Req 1: 動物一覧表示** | フロントエンド UI、APIクライアント、ページネーション | **Missing** | フロントエンドコンポーネント未実装 |
| **Req 2: 動物詳細表示** | フロントエンド UI、ルーティング、画像ギャラリー | **Missing** | ルーティング・詳細UIコンポーネント未実装 |
| **Req 3: 検索・フィルタリング** | フィルタUIコンポーネント、クエリパラメータ管理 | **Missing** | フィルタUIとクエリ状態管理未実装 |
| **Req 4: 自治体連絡先への誘導** | 電話リンク、外部リンク表示 | **Missing** | UIコンポーネント未実装 |
| **Req 5: レスポンシブデザイン** | CSS フレームワーク、メディアクエリ、lazy loading | **Missing** | スタイリングシステム未実装 |
| **Req 6: アクセシビリティ** | ARIA属性、セマンティックHTML、スクリーンリーダー対応 | **Missing** | アクセシビリティ対応未実装 |
| **Req 7: パフォーマンス** | 画像最適化、キャッシュ戦略、エラーハンドリング | **Missing** | フロントエンドパフォーマンス最適化未実装 |
| **バックエンドAPI** | REST API、フィルタリング、ページネーション | **Available** | `GET /animals`, `GET /animals/{id}` 実装済み |
| **CORS設定** | CORS ミドルウェア | **Available** | FastAPI アプリケーションに実装済み |
| **データスキーマ** | `category` フィールド | **Available** | `AnimalPublic` スキーマに `category` 含む |

### 2.2 ギャップ詳細

#### Missing: フロントエンド全体
- **フレームワーク**: React / Next.js / Vite などの選定と初期化が必要
- **UI コンポーネント**: 動物カード、詳細ページ、フィルタUI、ナビゲーション、フッター
- **状態管理**: フィルタ状態、ページネーション状態、API データキャッシュ
- **ルーティング**: `/` (一覧)、`/animals/{id}` (詳細) などのページルーティング
- **スタイリング**: CSS フレームワーク（Tailwind CSS / CSS Modules / styled-components など）
- **画像処理**: lazy loading、WebP変換、画像最適化
- **アクセシビリティ**: ARIA属性、キーボードナビゲーション、スクリーンリーダー対応
- **テスト**: フロントエンドテスト環境（Jest / Vitest / React Testing Library）

#### Unknown: デプロイ戦略
- **ホスティング**: Vercel / Netlify / GitHub Pages など（静的ホスティング）
- **ビルド設定**: 本番ビルド、開発サーバー、環境変数管理
- **API接続**: バックエンドAPIのURL設定（開発環境 vs 本番環境）

#### Constraint: モノリポ構成
- 現在 `data-collector` パッケージとして単一リポジトリ
- フロントエンドを別ディレクトリ（例: `frontend/` または `web-portal/`）として追加するか、別リポジトリとして分離するかの判断が必要

---

## 3. 実装アプローチオプション

### Option A: 完全新規作成（独立フロントエンド）

#### 概要
- フロントエンドを完全に新規プロジェクトとして作成
- `frontend/` または `web-portal/` ディレクトリ配下に配置
- バックエンドAPIとは独立したビルド・デプロイパイプライン

#### 適用対象
- すべてのフロントエンド機能（Req 1-7）

#### 統合ポイント
- **API呼び出し**: 環境変数で API_BASE_URL を設定し、`fetch()` または `axios` でバックエンドAPIにリクエスト
- **CORS**: すでに設定済みのため追加作業不要
- **データスキーマ**: `AnimalPublic` の TypeScript 型定義を作成（バックエンドスキーマと同期）

#### 責任境界
- **フロントエンド**: UI/UX、ルーティング、状態管理、アクセシビリティ、パフォーマンス最適化
- **バックエンド**: データ永続化、ビジネスロジック、API提供（変更なし）

#### Trade-offs
- ✅ **長所**:
  - フロントエンドとバックエンドの完全な分離（異なる技術スタック、デプロイ戦略）
  - 静的サイト生成（SSG）による高速なページロード、優れたSEO
  - 独立したスケーリング（Vercel/Netlifyなどのエッジデプロイ）
- ❌ **短所**:
  - 新規プロジェクトのセットアップコスト（ビルドツール、依存関係、設定ファイル）
  - 別々のデプロイパイプライン管理が必要
  - API URL の環境変数管理が必要

### Option B: モノリスアプローチ（FastAPI + Jinja2テンプレート）

#### 概要
- FastAPI のテンプレートエンジン（Jinja2）を使用してサーバーサイドレンダリング（SSR）
- `templates/` ディレクトリにHTMLテンプレート配置
- バックエンドと同じデプロイパイプライン

#### 適用対象
- すべてのフロントエンド機能（Req 1-7）

#### 統合ポイント
- **テンプレートレンダリング**: FastAPI ルーターでテンプレートを返す
- **静的アセット**: `static/` ディレクトリに CSS/JavaScript を配置
- **API呼び出し**: クライアントサイドJavaScriptで `/animals` エンドポイントを呼び出し

#### 責任境界
- **FastAPI**: ページルーティング、テンプレートレンダリング、API提供
- **クライアントサイドJS**: インタラクティブ機能（フィルタリング、ページネーション）

#### Trade-offs
- ✅ **長所**:
  - 単一デプロイパイプライン（シンプルな構成）
  - 既存の FastAPI プロジェクトに統合可能
  - サーバーサイドレンダリングによる初期ロードの高速化
- ❌ **短所**:
  - モダンなフロントエンドフレームワーク（React）の恩恵を受けにくい
  - コンポーネント再利用性が低い（Jinja2テンプレートは型安全性なし）
  - アクセシビリティやパフォーマンス最適化が複雑（手動管理）
  - SSG（静的サイト生成）の恩恵を受けられない

### Option C: ハイブリッドアプローチ（Next.js + API Routes）

#### 概要
- Next.js をフロントエンドフレームワークとして採用
- Next.js の API Routes をプロキシとして使用し、バックエンド FastAPI に転送
- `frontend/` ディレクトリに Next.js プロジェクト配置

#### 適用対象
- すべてのフロントエンド機能（Req 1-7）

#### 統合ポイント
- **API Proxy**: Next.js の API Routes で `/api/animals` → FastAPI `GET /animals` に転送
- **SSG/ISR**: 動物一覧ページを静的生成（Incremental Static Regeneration で定期更新）
- **CORS回避**: Next.js のサーバーサイドでバックエンドAPIを呼び出し、ブラウザからの直接アクセスを回避

#### 責任境界
- **Next.js**: フロントエンドUI、ルーティング、静的サイト生成、API Proxy
- **FastAPI**: データ永続化、ビジネスロジック、API提供（変更なし）

#### Trade-offs
- ✅ **長所**:
  - モダンなフロントエンド開発体験（React、TypeScript、型安全性）
  - SSG/ISR による高速なページロード、優れたSEO
  - API Routes によるバックエンドAPIの統合（CORS問題の回避）
  - アクセシビリティ・パフォーマンス最適化がフレームワークでサポート
- ❌ **短所**:
  - Next.js の学習コスト（App Router、Server Components など）
  - デプロイ複雑性（Vercel推奨だが、セルフホスティングも可能）
  - API Proxy 層の追加（レイテンシーの増加リスク）

---

## 4. 実装複雑性とリスク

### 工数見積もり

| アプローチ | 工数 | 理由 |
|-----------|------|------|
| **Option A: 完全新規作成** | **L (1-2週間)** | フロントエンドプロジェクトのセットアップ、全コンポーネント実装、API統合、テスト、デプロイ設定 |
| **Option B: モノリス** | **M (3-7日)** | Jinja2テンプレート作成、クライアントサイドJavaScript、静的アセット管理。ただし、アクセシビリティ対応が複雑化 |
| **Option C: ハイブリッド** | **L (1-2週間)** | Next.js セットアップ、コンポーネント実装、SSG/ISR設定、API Proxy実装、デプロイ設定 |

### リスク評価

| アプローチ | リスク | 理由 |
|-----------|--------|------|
| **Option A: 完全新規作成** | **Medium** | 新規フレームワーク（React/Vite）の導入、ビルド設定、デプロイパイプライン管理。ただし、既存のベストプラクティスが確立されており、技術的な未知数は少ない |
| **Option B: モノリス** | **High** | アクセシビリティ要件（Req 6）の達成が困難。WCAG 2.1 AA準拠には手動実装が必要で、テストが複雑。パフォーマンス最適化（Req 7）も手動管理 |
| **Option C: ハイブリッド** | **Low** | Next.js はアクセシビリティ・パフォーマンス最適化がフレームワークレベルでサポート。ISRによる静的生成で要件を満たしやすい。ただし、API Proxy層の実装品質が重要 |

---

## 5. 推奨事項

### 5.1 推奨アプローチ

**Option C: ハイブリッドアプローチ（Next.js + API Routes）** を推奨します。

#### 推奨理由
1. **要件適合性**: アクセシビリティ（Req 6）、パフォーマンス（Req 7）、レスポンシブデザイン（Req 5）が Next.js のベストプラクティスで自然にサポートされる
2. **SEO最適化**: 静的サイト生成（SSG）により初期ロードが高速で、検索エンジンに優しい
3. **型安全性**: TypeScript + React で既存のバックエンド Pydantic スキーマと対応する型定義を作成可能
4. **将来性**: Next.js は 2026年現在も主流のフレームワークであり、コミュニティサポートが豊富
5. **開発体験**: React の豊富なエコシステム（UI ライブラリ、テストツール、開発ツール）を活用可能

#### 代替案
- **Option A（完全新規作成）も有力**: Vite + React + TypeScript で軽量な構成も可能。ただし、SSG/ISR の恩恵を受けるには追加のツール（Astro など）が必要
- **Option Bは非推奨**: アクセシビリティとパフォーマンス要件を満たすコストが高すぎる

### 5.2 設計フェーズで検討すべき事項

#### 技術選定
- **フロントエンドフレームワーク**: Next.js 15+ (App Router) vs Next.js 14 (Pages Router) vs Vite + React
- **UIライブラリ**: Tailwind CSS vs CSS Modules vs styled-components
- **状態管理**: React Context vs Zustand vs TanStack Query（サーバー状態管理）
- **フォーム管理**: React Hook Form vs Formik（フィルタリングUIで使用）
- **画像最適化**: Next.js Image Optimization vs Cloudinary vs 手動最適化
- **テストツール**: Jest + React Testing Library vs Vitest + React Testing Library
- **アクセシビリティ検証**: axe-core, Lighthouse, WAVE

#### デプロイ戦略
- **ホスティング**: Vercel（推奨）vs Netlify vs セルフホスティング（Docker + Nginx）
- **環境変数**: 開発環境 API URL vs 本番環境 API URL
- **CI/CD**: GitHub Actions でビルド・デプロイ自動化

#### API統合
- **API Proxy設計**: Next.js API Routes でバックエンドAPIを呼び出す方式 vs ブラウザから直接呼び出す方式（CORS利用）
- **データキャッシュ**: TanStack Query によるクライアントサイドキャッシュ vs Next.js ISR によるサーバーサイドキャッシュ
- **TypeScript型定義**: バックエンド Pydantic スキーマから自動生成 vs 手動同期

#### プロジェクト構成
- **ディレクトリ配置**: `frontend/` vs `web-portal/` vs 別リポジトリ
- **モノリポ管理**: 単一リポジトリで `backend/` と `frontend/` を管理 vs 別々のリポジトリ

### 5.3 リサーチが必要な領域

1. **Next.js のレンダリング戦略**: SSG vs ISR vs SSR の選択基準（動物データの更新頻度に依存）
2. **画像最適化戦略**: バックエンドから提供される画像URLをどのように最適化するか（Next.js Image vs Cloudinary）
3. **アクセシビリティテスト自動化**: CI/CDパイプラインに axe-core を統合する方法
4. **パフォーマンスモニタリング**: Lighthouse CI によるパフォーマンス継続的監視

---

## 6. 要件-アセットマップ（詳細）

### Requirement 1: 動物一覧表示

| 機能 | 必要なアセット | 現在の状態 | ギャップ |
|------|----------------|-----------|---------|
| 動物一覧取得 | `GET /animals` API | ✅ Available | - |
| 動物カード表示 | React コンポーネント | ❌ Missing | 動物カードコンポーネント実装が必要 |
| カテゴリラベル | UI コンポーネント | ❌ Missing | カテゴリバッジコンポーネント実装が必要 |
| ページネーション | UI コンポーネント、状態管理 | ❌ Missing | ページネーションコンポーネント、offset/limit 状態管理が必要 |
| 空状態表示 | UI コンポーネント | ❌ Missing | 空状態コンポーネント実装が必要 |
| ソート（収容日降順） | API サポート | ✅ Available | バックエンドで実装済み |

### Requirement 2: 動物詳細表示

| 機能 | 必要なアセット | 現在の状態 | ギャップ |
|------|----------------|-----------|---------|
| 動物詳細取得 | `GET /animals/{id}` API | ✅ Available | - |
| 詳細ページUI | React コンポーネント | ❌ Missing | 詳細ページコンポーネント実装が必要 |
| 画像ギャラリー | UI コンポーネント | ❌ Missing | 画像ギャラリーコンポーネント、モーダル実装が必要 |
| 元ページリンク | UI コンポーネント | ❌ Missing | 外部リンクコンポーネント実装が必要 |
| ナビゲーション | ルーティング | ❌ Missing | ルーティング設定（`/animals/{id}`）が必要 |
| エラーハンドリング（404） | エラーページ | ❌ Missing | 404エラーページコンポーネント実装が必要 |

### Requirement 3: 検索・フィルタリング機能

| 機能 | 必要なアセット | 現在の状態 | ギャップ |
|------|----------------|-----------|---------|
| カテゴリフィルタ | API サポート、UI コンポーネント | ⚠️ Partial | API実装済み、UIコンポーネント未実装 |
| 種別フィルタ | API サポート、UI コンポーネント | ⚠️ Partial | API実装済み、UIコンポーネント未実装 |
| 性別フィルタ | API サポート、UI コンポーネント | ⚠️ Partial | API実装済み、UIコンポーネント未実装 |
| 地域フィルタ | API サポート、UI コンポーネント | ⚠️ Partial | API実装済み（部分一致）、UIコンポーネント未実装 |
| フィルタ状態管理 | React 状態管理 | ❌ Missing | クエリパラメータ同期、フィルタ状態管理が必要 |
| フィルタクリア | UI コンポーネント | ❌ Missing | フィルタクリアボタン実装が必要 |
| 結果件数表示 | API サポート、UI コンポーネント | ⚠️ Partial | API実装済み（`total_count`）、UIコンポーネント未実装 |

### Requirement 4: 自治体連絡先への誘導

| 機能 | 必要なアセット | 現在の状態 | ギャップ |
|------|----------------|-----------|---------|
| 電話番号表示 | API サポート、UI コンポーネント | ⚠️ Partial | API実装済み（`phone`）、UIコンポーネント未実装 |
| 電話リンク（tel:） | UI コンポーネント | ❌ Missing | `tel:` リンクコンポーネント実装が必要 |
| カテゴリ別案内文 | UI コンポーネント | ❌ Missing | 条件分岐による案内文表示が必要 |
| 元ページリンク | API サポート、UI コンポーネント | ⚠️ Partial | API実装済み（`source_url`）、UIコンポーネント未実装 |
| フッター（利用規約） | UI コンポーネント | ❌ Missing | フッターコンポーネント実装が必要 |

### Requirement 5: レスポンシブデザイン

| 機能 | 必要なアセット | 現在の状態 | ギャップ |
|------|----------------|-----------|---------|
| ブレークポイント設定 | CSS フレームワーク | ❌ Missing | Tailwind CSS / CSS Modules でブレークポイント設定が必要 |
| グリッドレイアウト | CSS コンポーネント | ❌ Missing | レスポンシブグリッド実装が必要 |
| タッチ対応ボタン | UI コンポーネント | ❌ Missing | タッチターゲットサイズ（44x44px）実装が必要 |
| 画像 lazy loading | 画像コンポーネント | ❌ Missing | Next.js Image または HTML `loading="lazy"` 実装が必要 |

### Requirement 6: アクセシビリティ

| 機能 | 必要なアセット | 現在の状態 | ギャップ |
|------|----------------|-----------|---------|
| 代替テキスト | 画像コンポーネント | ❌ Missing | `alt` 属性の適切な設定が必要 |
| キーボードナビゲーション | UI コンポーネント | ❌ Missing | `tabIndex`, `onKeyDown` 実装が必要 |
| フォーカス表示 | CSS スタイル | ❌ Missing | `:focus-visible` スタイル実装が必要 |
| 見出し構造 | HTML セマンティクス | ❌ Missing | `h1`-`h6` の適切な階層実装が必要 |
| コントラスト比 | デザインシステム | ❌ Missing | WCAG 2.1 AA（4.5:1）準拠のカラーパレット設定が必要 |
| ランドマーク要素 | HTML セマンティクス | ❌ Missing | `header`, `nav`, `main`, `footer` 実装が必要 |

### Requirement 7: パフォーマンス

| 機能 | 必要なアセット | 現在の状態 | ギャップ |
|------|----------------|-----------|---------|
| 初期ロード3秒以内 | SSG/ISR | ❌ Missing | Next.js SSG/ISR 実装が必要 |
| LCP 2.5秒以内 | パフォーマンス最適化 | ❌ Missing | 画像最適化、コード分割が必要 |
| 画像最適化（WebP） | 画像処理 | ❌ Missing | Next.js Image または手動変換が必要 |
| キャッシュヘッダー | サーバー設定 | ❌ Missing | Next.js ビルド設定またはホスティング設定が必要 |
| ローディングUI | UI コンポーネント | ❌ Missing | スケルトンスクリーンまたはスピナー実装が必要 |
| エラーハンドリング | UI コンポーネント | ❌ Missing | エラーバウンダリ、再試行ボタン実装が必要 |

---

## 7. まとめ

### 分析結果サマリー

- **既存アセット**: バックエンドAPIは完全に実装済み（`GET /animals`, `GET /animals/{id}`, `category` フィルタ対応）
- **主要ギャップ**: フロントエンドが完全に未実装（React コンポーネント、ルーティング、状態管理、スタイリング、テスト）
- **推奨アプローチ**: Option C（Next.js + API Routes）による完全新規作成
- **工数**: L (1-2週間)
- **リスク**: Low（Next.js によるアクセシビリティ・パフォーマンス最適化のフレームワークサポート）

### 次のステップ

設計フェーズに進む前に、以下の意思決定を行ってください：

1. **フロントエンドフレームワーク選定**: Next.js vs Vite + React
2. **UIライブラリ選定**: Tailwind CSS vs CSS Modules vs styled-components
3. **デプロイ戦略**: Vercel vs Netlify vs セルフホスティング
4. **プロジェクト構成**: モノリポ（`frontend/`）vs 別リポジトリ

設計フェーズでは、上記の技術選定に基づいて詳細なアーキテクチャ設計、コンポーネント設計、API統合設計を行います。

---

**次のコマンド**: `/kiro:spec-design public-web-portal` で技術設計フェーズに進んでください。

Sources:
- [React vs. Next.js: A 2026 Developer's Guide to Differences and Use Cases](https://sam-solutions.com/blog/react-vs-nextjs/)
- [Next.js by Vercel - The React Framework](https://nextjs.org/)
- [Next JS vs React : Which Framework to choose for Front end in 2026?](https://medium.com/predict/next-js-vs-react-which-framework-to-choose-for-front-end-in-2026-865425fdda1c)
- [Rendering: Static Site Generation (SSG) | Next.js](https://nextjs.org/docs/pages/building-your-application/rendering/static-site-generation)
- [React-based Static Site Generators in 2025](https://crystallize.com/blog/react-static-site-generators)
- [Accessibility in React: Best Practices](https://medium.com/@ignatovich.dm/accessibility-in-react-best-practices-for-building-inclusive-web-apps-906d1cbedd27)
- [Accessibility Testing in React: Tools and Best Practices](https://medium.com/@ignatovich.dm/accessibility-testing-in-react-tools-and-best-practices-119f3c0aee6e)
- [React Accessibility (A11y) Best Practices](https://rtcamp.com/handbook/react-best-practices/accessibility/)
- [Accessibility Beyond Basics: Implementing WCAG 2.1 Standards](https://dev.to/joshuawasike/accessibility-beyond-basics-implementing-wcag-21-standards-in-modern-web-apps-75b)
- [React Accessibility: Best Practices Guide for WCAG-Compliant SPAs](https://www.allaccessible.org/blog/react-accessibility-best-practices-guide)
