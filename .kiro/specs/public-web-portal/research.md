# リサーチ & 設計決定

## Summary
- **Feature**: `public-web-portal`
- **Discovery Scope**: New Feature (Greenfield)
- **Key Findings**:
  - Next.js 15 App Routerが2026年のベストプラクティス（React Server Components、優れたパフォーマンス、SEO最適化）
  - TanStack Query v5がReact Server Componentsと組み合わせることで、サーバー初期ロード + クライアントサイドキャッシングの最適なハイブリッドアーキテクチャを実現
  - Next.js Imageコンポーネントが外部URL画像の自動WebP変換とレスポンシブ最適化をサポート
  - Tailwind CSSでWCAG 2.1 AA準拠のカラーパレット設計が必要（コントラスト比4.5:1以上）

## Research Log

### Next.js 15: App Router vs Pages Router

- **Context**: フロントエンドフレームワークとしてNext.jsを採用する場合、App RouterとPages Routerのどちらを選択すべきか調査
- **Sources Consulted**:
  - [Next.js App Router vs Pages Router Comparison - Pagepro](https://pagepro.co/blog/app-router-vs-page-router-comparison/)
  - [How to Choose Between App Router and Pages Router in Next.js 15 - Wisp CMS](https://www.wisp.blog/blog/how-to-choose-between-app-router-and-pages-router-in-nextjs-15-a-complete-guide-for-seo-conscious-developers)
  - [Stop Choosing Wrong: Next.js 15 App Router vs Pages Router Performance Reality Check - Markaicode](https://markaicode.com/nextjs-15-router-performance-comparison/)

- **Findings**:
  - **App Router（推奨）**:
    - React Server Components（RSC）による初期JavaScript削減とCore Web Vitals改善
    - 直感的なネストレイアウト、`app/` フォルダ構造
    - 2026年の標準、Reactエコシステムと密接に統合
    - Server Componentsによりブラウザに送信するJavaScriptを削減し、LCP（Largest Contentful Paint）の高速化
  - **Pages Router（レガシー）**:
    - `pages/` フォルダ、従来のルートベースデータフェッチング
    - 既存プロジェクトのメンテナンスには適しているが、新規プロジェクトには非推奨
  - **課題**:
    - Server Components vs Client Componentsのメンタルモデル理解が必要
    - サーバーサイド・クライアントサイド実行の区別によるデバッグの複雑性

- **Implications**:
  - 新規プロジェクトではApp Routerを採用すべき（パフォーマンス、将来性、SEO最適化）
  - `app/` ディレクトリ構造でルーティングを設計
  - Server ComponentsとClient Componentsの明確な分離が必要

### TanStack Query v5: サーバー状態管理とキャッシング戦略

- **Context**: React Server ComponentsとクライアントサイドAPIデータキャッシングの統合方法を調査
- **Sources Consulted**:
  - [React Server Components + TanStack Query: The 2026 Data-Fetching Power Duo - DEV Community](https://dev.to/krish_kakadiya_5f0eaf6342/react-server-components-tanstack-query-the-2026-data-fetching-power-duo-you-cant-ignore-21fj)
  - [TanStack Query Overview - TanStack Docs](https://tanstack.com/query/latest/docs/framework/react/overview)
  - [Caching Examples - TanStack Query Docs](https://tanstack.com/query/v5/docs/react/guides/caching)
  - [Seamless Server State Management in Next.js with TanStack Query - Leapcell](https://leapcell.io/blog/seamless-server-state-management-in-next-js-with-tanstack-query)

- **Findings**:
  - **ハイブリッドアーキテクチャ（2026年ベストプラクティス）**:
    - React Server Componentsでサーバー初期ロード（高速初期表示）
    - TanStack Queryでクライアントサイドキャッシング、mutation、バックグラウンド再フェッチ
  - **自動キャッシング**:
    - Stale-While-Revalidate戦略: キャッシュデータを即座に表示しつつ、バックグラウンドで最新データを取得
    - デフォルトでは `staleTime: 0`（即座にstale扱い）、二重フェッチを避けるため適切な `staleTime` 設定が推奨
  - **主要機能**:
    - Infinite scrolling、Optimistic UI、リクエストデduplication、バックグラウンド同期
    - TanStack Query v5はReact Server Components対応とSuspense統合が改善

- **Implications**:
  - TanStack Query v5をクライアントサイド状態管理に採用
  - Server ComponentsとClient Componentsの役割分担: Server → 初期データフェッチ、Client → インタラクティブ機能（フィルタリング、ページネーション）
  - `staleTime` と `cacheTime` の適切な設定でパフォーマンス最適化

### Tailwind CSS: アクセシビリティとWCAG 2.1 AA準拠

- **Context**: レスポンシブデザインとアクセシビリティ要件を満たすCSSフレームワークの選定
- **Sources Consulted**:
  - [InclusiveColors: WCAG accessible color palette creator for Tailwind/CSS/Figma/Adobe](https://www.inclusivecolors.com/)
  - [Solving Common Accessibility Issues in Tailwind CSS for Better UX - Medium](https://medium.com/@mohantaankit2002/solving-common-accessibility-issues-in-tailwind-css-for-better-ux-577bc84b9649)
  - [Color Contrast Accessibility: Complete WCAG 2025 Guide - AllAccessible Blog](https://www.allaccessible.org/blog/color-contrast-accessibility-wcag-guide-2025)
  - [The Accessibility Conversation: Making Tailwind CSS Projects Inclusive - fsjs.dev](https://fsjs.dev/the-accessibility-conversation-tailwind-css-inclusive/)

- **Findings**:
  - **WCAG 2.1 AA コントラスト要件**:
    - 通常テキスト: 4.5:1以上のコントラスト比
    - 大きいテキスト（14pt太字または18pt以上）: 3:1以上
  - **Tailwind CSS対応**:
    - デフォルトパレットは有用だが、テキスト・UI要素のコントラスト比を常にチェックする必要がある
    - InclusiveColorsなどのツールでWCAG準拠カラーパレット生成が可能
  - **ベストプラクティス**:
    - ARIA属性の適切な使用、支援技術でのテスト
    - WebAIMのコントラストチェッカーでカラーコンビネーションを検証
  - **法的コンテキスト**:
    - 米国司法省が2024年4月にADA Title II更新、2026年（5万人以上対象）と2027年（5万人未満対象）にコンプライアンス期限

- **Implications**:
  - Tailwind CSSを採用し、WCAG 2.1 AA準拠のカスタムカラーパレット設計が必須
  - 開発段階でWebAIMコントラストチェッカー、Lighthouse、axe-coreで継続的に検証
  - フォーカス状態、キーボードナビゲーション、スクリーンリーダー対応をTailwindユーティリティで実装

### Next.js Image: 外部URL画像の最適化とWebP変換

- **Context**: バックエンドAPIから提供される外部画像URLの最適化戦略を調査
- **Sources Consulted**:
  - [Getting Started: Image Optimization - Next.js](https://nextjs.org/docs/app/getting-started/images)
  - [Next.js Image Optimization: A Guide for Web Developers - Strapi](https://strapi.io/blog/nextjs-image-optimization-developers-guide)
  - [Image optimization for Next.js with imgproxy - imgproxy Blog](https://imgproxy.net/blog/image-optimization-for-nextjs-with-imgproxy/)
  - [Next.js Image Optimization - DebugBear](https://www.debugbear.com/blog/nextjs-image-optimization)

- **Findings**:
  - **自動WebP変換**:
    - Next.js `<Image>` コンポーネントがブラウザの `Accept` ヘッダーを自動検査し、WebP/AVIF/JPEGの最適なフォーマットを選択
    - Sharp圧縮により40-70%のファイルサイズ削減、WebP/AVIF変換でさらに25-35%削減
  - **外部URL設定**:
    - `next.config.js` で `remotePatterns` 設定が必要
    - 初回訪問時にオンデマンド処理、以降はキャッシュから配信（ビルド時ではなくランタイム最適化）
  - **レスポンシブ対応**:
    - デバイスごとに適切なサイズの画像を自動配信
    - `w`（幅）、`q`（品質）クエリパラメータで最適化された画像URL生成（例: `/_next/image?url=...&w=750&q=75`）
  - **検証方法**:
    - Response Headersで `Content-Type: image/webp` または `image/avif` を確認
    - Proxy/CDN使用時は `Accept` ヘッダーの転送設定が必要

- **Implications**:
  - Next.js `<Image>` コンポーネントを全画像に使用し、外部URL画像を自動最適化
  - `next.config.js` の `remotePatterns` でバックエンドAPIドメイン（およびサードパーティ画像サービス）を許可
  - Lazy loading、レスポンシブ画像サイズ、WebP/AVIF変換が自動的に適用されるため、Requirement 5, 7を満たしやすい

### バックエンドAPI統合: FastAPI CORS設定とTypeScript型定義

- **Context**: 既存FastAPIバックエンドとNext.jsフロントエンドの統合方法を調査
- **Sources Consulted**: ギャップ分析、既存コードベース（`src/data_collector/infrastructure/api/`）

- **Findings**:
  - **既存CORS設定**:
    - FastAPIで `CORSMiddleware` 設定済み（`CORS_ORIGINS` 環境変数で制御）
    - `allow_credentials`, `allow_methods`, `allow_headers` すべて許可済み
  - **API エンドポイント**:
    - `GET /animals`: フィルタリング（`species`, `sex`, `location`, `category`, `shelter_date_from`, `shelter_date_to`）、ページネーション（`limit`, `offset`）対応
    - `GET /animals/{id}`: 個別動物データ取得
    - レスポンス: `PaginatedResponse<AnimalPublic>` (JSON)
  - **データスキーマ**:
    - `AnimalPublic`: `id`, `species`, `sex`, `age_months`, `color`, `size`, `shelter_date`, `location`, `phone`, `image_urls`, `source_url`, `category`

- **Implications**:
  - Next.jsクライアントから直接FastAPI `/animals` エンドポイントを呼び出し可能（CORS設定済み）
  - TypeScript型定義を `AnimalPublic` Pydanticスキーマに対応させて作成
  - TanStack Queryで `/animals` エンドポイントをラップし、キャッシング・再フェッチ戦略を実装

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| **Next.js App Router + TanStack Query (選択)** | React Server ComponentsとTanStack Query v5のハイブリッド | SSG/ISR、優れたSEO、型安全性、自動WebP変換、アクセシビリティサポート | App Router学習コスト、Server/Client Components区別 | 2026年ベストプラクティス、gap-analysis.mdで推奨されたOption C |
| **Vite + React SPA** | 完全クライアントサイドSPA | 軽量、高速開発サーバー、シンプル | SSGなし（SEO不利）、画像最適化手動、初期ロード遅い | SSG/ISR不要の場合は有力だが、Requirement 7（パフォーマンス）を満たしにくい |
| **FastAPI + Jinja2** | サーバーサイドレンダリング（SSR） | 単一デプロイ、シンプル構成 | モダンフレームワーク恩恵なし、アクセシビリティ手動実装、型安全性低い | gap-analysis.mdで非推奨（アクセシビリティ・パフォーマンス要件達成コスト高） |

**選定理由**: Next.js App Router + TanStack Queryは、Requirement 5（レスポンシブ）、Requirement 6（アクセシビリティ）、Requirement 7（パフォーマンス）をフレームワークレベルで自然にサポートし、実装コストとリスクを最小化。

## Design Decisions

### Decision: Next.js 15 App Router採用

- **Context**: フロントエンドフレームワークとルーティングメカニズムの選定
- **Alternatives Considered**:
  1. **Next.js 15 App Router** — React Server Components、SSG/ISR、自動画像最適化
  2. **Next.js 14 Pages Router** — 従来のルーティング、レガシーサポート
  3. **Vite + React Router** — 軽量SPA、SSGなし
- **Selected Approach**: Next.js 15 App Router
- **Rationale**:
  - React Server Componentsによる初期JavaScript削減とLCP改善（Requirement 7: LCP 2.5秒以内）
  - SSG（Static Site Generation）により初期ロード3秒以内を達成可能（Requirement 7.1）
  - Next.js Imageコンポーネントが画像最適化（WebP、lazy loading）を自動処理（Requirement 5.6, 7.3）
  - 2026年の標準、Reactエコシステムと密接統合
- **Trade-offs**:
  - ✅ パフォーマンス、SEO、開発体験
  - ❌ App Router学習コスト、Server/Client Components区別の複雑性
- **Follow-up**: Server ComponentsとClient Componentsの責任境界を明確化、開発チームへのトレーニング

### Decision: TanStack Query v5 採用

- **Context**: クライアントサイドAPIデータキャッシングと状態管理の選定
- **Alternatives Considered**:
  1. **TanStack Query v5** — サーバー状態管理、自動キャッシング、React Server Components対応
  2. **React Context + useState** — シンプル、軽量、手動キャッシング
  3. **Zustand** — グローバル状態管理、サーバー状態特化なし
- **Selected Approach**: TanStack Query v5
- **Rationale**:
  - Stale-While-Revalidate戦略により、キャッシュデータ即座表示 + バックグラウンド再フェッチ
  - Infinite scrolling、Optimistic UI、リクエストdeduplicationをビルトインサポート
  - React Server Componentsと組み合わせることで、サーバー初期ロード + クライアントキャッシングの最適なハイブリッド（2026年ベストプラクティス）
- **Trade-offs**:
  - ✅ 自動キャッシング、パフォーマンス最適化、開発効率
  - ❌ ライブラリ依存、学習コスト
- **Follow-up**: `staleTime`, `cacheTime` の適切な設定、Error Boundaryとの統合

### Decision: Tailwind CSS v4 採用

- **Context**: スタイリングフレームワークとレスポンシブデザインの実装
- **Alternatives Considered**:
  1. **Tailwind CSS v4** — ユーティリティファースト、レスポンシブ対応、WCAG準拠カラーパレット設計可能
  2. **CSS Modules** — スコープ付きCSS、完全カスタム
  3. **styled-components** — CSS-in-JS、動的スタイリング
- **Selected Approach**: Tailwind CSS v4
- **Rationale**:
  - レスポンシブブレークポイント（`sm`, `md`, `lg`）をユーティリティクラスで簡潔に記述（Requirement 5.1-5.4）
  - WCAG 2.1 AA準拠のカスタムカラーパレット設計が可能（Requirement 6.5）
  - ユーティリティクラスでフォーカス状態（`focus:ring`）、キーボードナビゲーション対応が容易（Requirement 6.2-6.3）
  - 軽量、ビルド時に未使用CSSを自動削除（パフォーマンス最適化）
- **Trade-offs**:
  - ✅ 開発効率、レスポンシブ対応、アクセシビリティ
  - ❌ HTMLクラス名の冗長性、学習コスト
- **Follow-up**: カスタムカラーパレット設計（InclusiveColors、WebAIMコントラストチェッカー使用）、Tailwind設定ファイルでWCAG準拠カラー定義

### Decision: プロジェクト構成 — モノリポ `frontend/` ディレクトリ

- **Context**: フロントエンドプロジェクトの配置場所と既存バックエンドとの関係
- **Alternatives Considered**:
  1. **モノリポ `frontend/` ディレクトリ** — 単一リポジトリで `src/` (バックエンド) と `frontend/` (フロントエンド) を管理
  2. **モノリポ `web-portal/` ディレクトリ** — 機能名ベースのディレクトリ名
  3. **別リポジトリ** — フロントエンドとバックエンドを完全に分離
- **Selected Approach**: モノリポ `frontend/` ディレクトリ
- **Rationale**:
  - 単一リポジトリでバージョン管理、CI/CD統合が容易
  - 型定義（TypeScript）をバックエンドPydanticスキーマから生成する場合、同一リポジトリが便利
  - 開発環境でバックエンド（FastAPI）とフロントエンド（Next.js）を並行実行可能
- **Trade-offs**:
  - ✅ シンプルな構成、型定義共有、CI/CD統合
  - ❌ デプロイパイプラインが複雑化（フロントエンドとバックエンドで異なるホスティング）
- **Follow-up**: CI/CD設定でフロントエンド（Vercel/Netlify）とバックエンド（セルフホスティング/クラウド）の分離デプロイを設計

### Decision: デプロイ戦略 — Vercel（フロントエンド）+ セルフホスティング（バックエンド）

- **Context**: フロントエンドとバックエンドのデプロイ先選定
- **Alternatives Considered**:
  1. **Vercel（フロントエンド）+ セルフホスティング（バックエンド）** — Next.jsの最適化、独立したスケーリング
  2. **Netlify（フロントエンド）+ セルフホスティング（バックエンド）** — 静的サイトホスティング特化
  3. **Docker + Nginx（フロントエンド+バックエンド統合）** — 単一デプロイ、複雑な設定
- **Selected Approach**: Vercel（フロントエンド）+ セルフホスティング（バックエンド）
- **Rationale**:
  - VercelはNext.jsの公式推奨ホスティング、自動最適化（Edge Functions、ISR、画像最適化）
  - フロントエンドとバックエンドの独立したスケーリング、デプロイサイクル分離
  - 環境変数で `API_BASE_URL` を設定し、開発環境と本番環境を切り替え
- **Trade-offs**:
  - ✅ Next.js最適化、高速デプロイ、エッジデプロイ
  - ❌ Vercel無料プランの制限、別々のデプロイパイプライン管理
- **Follow-up**: 環境変数設定（`.env.local`, `.env.production`）、CI/CD設定（GitHub Actions）

## Risks & Mitigations

- **Risk 1: Server Components vs Client Components の混乱** — 開発チームがApp Routerのメンタルモデルを理解せず、パフォーマンス最適化を逃す
  - **Mitigation**: コンポーネント設計ガイドライン作成、Server/Client境界を明確化、レビュープロセスで確認

- **Risk 2: WCAG 2.1 AA準拠カラーパレット設計の不備** — コントラスト比不足によりアクセシビリティ要件未達成
  - **Mitigation**: InclusiveColors、WebAIMコントラストチェッカーで全カラーコンビネーションを検証、CI/CDでLighthouse/axe-core自動テスト

- **Risk 3: 外部画像URL最適化のパフォーマンス問題** — 初回訪問時の画像処理遅延によりLCP悪化
  - **Mitigation**: `next.config.js` でキャッシュ設定最適化、CDN利用、`priority` プロパティで重要画像を優先処理

- **Risk 4: TanStack Query設定不備によるキャッシュ効率低下** — `staleTime`, `cacheTime` 未設定で二重フェッチ発生
  - **Mitigation**: デフォルト設定を `staleTime: 5 * 60 * 1000` (5分) に設定、動物データ更新頻度に応じて調整

## References

### Next.js 15 App Router
- [Next.js App Router vs Pages Router Comparison - Pagepro](https://pagepro.co/blog/app-router-vs-page-router-comparison/)
- [How to Choose Between App Router and Pages Router in Next.js 15 - Wisp CMS](https://www.wisp.blog/blog/how-to-choose-between-app-router-and-pages-router-in-nextjs-15-a-complete-guide-for-seo-conscious-developers)
- [Stop Choosing Wrong: Next.js 15 App Router vs Pages Router Performance Reality Check - Markaicode](https://markaicode.com/nextjs-15-router-performance-comparison/)

### TanStack Query
- [React Server Components + TanStack Query: The 2026 Data-Fetching Power Duo - DEV Community](https://dev.to/krish_kakadiya_5f0eaf6342/react-server-components-tanstack-query-the-2026-data-fetching-power-duo-you-cant-ignore-21fj)
- [TanStack Query Overview - TanStack Docs](https://tanstack.com/query/latest/docs/framework/react/overview)
- [Caching Examples - TanStack Query Docs](https://tanstack.com/query/v5/docs/react/guides/caching)
- [Seamless Server State Management in Next.js with TanStack Query - Leapcell](https://leapcell.io/blog/seamless-server-state-management-in-next-js-with-tanstack-query)

### Tailwind CSS & Accessibility
- [InclusiveColors: WCAG accessible color palette creator for Tailwind/CSS/Figma/Adobe](https://www.inclusivecolors.com/)
- [Solving Common Accessibility Issues in Tailwind CSS for Better UX - Medium](https://medium.com/@mohantaankit2002/solving-common-accessibility-issues-in-tailwind-css-for-better-ux-577bc84b9649)
- [Color Contrast Accessibility: Complete WCAG 2025 Guide - AllAccessible Blog](https://www.allaccessible.org/blog/color-contrast-accessibility-wcag-guide-2025)
- [The Accessibility Conversation: Making Tailwind CSS Projects Inclusive - fsjs.dev](https://fsjs.dev/the-accessibility-conversation-tailwind-css-inclusive/)

### Next.js Image Optimization
- [Getting Started: Image Optimization - Next.js](https://nextjs.org/docs/app/getting-started/images)
- [Next.js Image Optimization: A Guide for Web Developers - Strapi](https://strapi.io/blog/nextjs-image-optimization-developers-guide)
- [Image optimization for Next.js with imgproxy - imgproxy Blog](https://imgproxy.net/blog/image-optimization-for-nextjs-with-imgproxy/)
- [Next.js Image Optimization - DebugBear](https://www.debugbear.com/blog/nextjs-image-optimization)
