# 実装計画

## タスクリスト

### セットアップ・基盤構築

- [x] 1. (P) Next.js プロジェクト初期化とTypeScript型定義作成
- [x] 1.1 (P) Next.js 15プロジェクトをApp Routerで初期化し、必要な依存関係をインストールする
  - `frontend/` ディレクトリ配下にNext.js 15 App Routerプロジェクトを作成
  - TypeScript、Tailwind CSS v4、TanStack Query v5、React Testing Library、Vitest、axe-coreをインストール
  - `tsconfig.json` でstrict modeを有効化し、`any` 型を禁止
  - _Requirements: 7.1, 7.2_

- [x] 1.2 (P) バックエンドAPIスキーマに対応するTypeScript型定義を作成する
  - `AnimalPublic` 型定義（id, species, sex, age_months, color, size, shelter_date, location, phone, image_urls, source_url, category）
  - `PaginatedResponse<T>` ジェネリック型定義（items, meta）
  - `PaginationMeta` 型定義（total_count, limit, offset, current_page, total_pages, has_next）
  - `FilterState` 型定義（category, species, sex, location）
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 2.1, 2.2, 2.3, 3.1, 3.2, 3.3, 3.4_

- [x] 1.3 (P) Tailwind CSSのWCAG 2.1 AA準拠カラーパレットを設計し設定する
  - `tailwind.config.ts` にカスタムカラーパレットを定義（primary, text, category）
  - WebAIMコントラストチェッカーで全カラーコンビネーションを検証（コントラスト比4.5:1以上）
  - フォーカス状態スタイル（`focus:ring`）をTailwindユーティリティで設定
  - _Requirements: 6.3, 6.5_

- [x] 1.4 (P) Next.js設定で外部画像URL最適化とCSPヘッダーを設定する
  - `next.config.js` の `remotePatterns` に高知県動物愛護センター（`**.kochi-apc.com`）を追加
  - WebP/AVIF自動変換を有効化（`formats: ['image/webp', 'image/avif']`）
  - Content Security Policyヘッダーを設定（`img-src` で外部画像ドメイン許可）
  - _Requirements: 5.6, 7.3_

- [x] 1.5 (P) TanStack Query デフォルト設定を構成する
  - `lib/queryClient.ts` でQueryClientを作成し、デフォルト設定を定義
  - `staleTime: 5分`, `cacheTime: 10分`, `retry: 3`, exponential backoffを設定
  - React Server ComponentsとClient Componentsの役割分担を明確化（Server → 初期データフェッチ、Client → インタラクティブ機能）
  - _Requirements: 1.5, 3.5, 7.5, 7.6_

### コアUIコンポーネント構築

- [x] 2. (P) 基本UIコンポーネントとレイアウトを実装する
- [x] 2.1 (P) ランドマーク要素を使用したレイアウトコンポーネントを作成する
  - `<header>`, `<nav>`, `<main>`, `<footer>` でページ構造を定義
  - ロゴ、サイトタイトル、ナビゲーションリンクをヘッダーに配置
  - 利用規約と免責事項（情報の正確性は自治体サイトを参照）をフッターに表示
  - レスポンシブブレークポイント（モバイル: 〜767px、タブレット: 768px〜1023px、デスクトップ: 1024px〜）をTailwindで設定
  - _Requirements: 4.6, 5.1, 6.6_

- [x] 2.2 (P) カテゴリバッジコンポーネントを作成する
  - 「譲渡対象」（adoption）と「迷子」（lost）のラベルを表示
  - カテゴリごとに異なる背景色を適用（WCAG 2.1 AA準拠カラー）
  - セマンティックなHTMLタグ（`<span role="status"`）を使用
  - _Requirements: 1.3, 2.2_

- [x] 2.3 (P) ローディングスピナーコンポーネントを作成する
  - TanStack Query `isLoading` 状態でスピナーを表示
  - アクセシブルなARIA属性（`aria-label="読み込み中"`）を設定
  - _Requirements: 7.5_

- [x] 2.4 (P) 空状態コンポーネントを作成する
  - 「現在表示できる動物がいません」というメッセージを表示
  - 「フィルタをクリア」ボタンを提供（フィルタが適用されている場合）
  - セマンティックなHTMLタグ（`<div role="alert"`）を使用
  - _Requirements: 1.6_

- [x] 2.5 (P) エラーバウンダリコンポーネントを作成する
  - TanStack Query `error` 状態でエラーメッセージと「再試行」ボタンを表示
  - ユーザーフレンドリーなエラーメッセージ（「APIに接続できませんでした。しばらくしてから再試行してください。」）
  - 「再試行」ボタンでTanStack Query refetchを実行
  - _Requirements: 7.6_

### 動物一覧ページ実装

- [x] 3. 動物一覧ページとフィルタリング機能を実装する
- [x] 3.1 トップページ（HomePage）をServer Componentで実装する
  - `app/page.tsx` で初期動物一覧データをサーバーサイドフェッチ（`GET /animals?limit=20&offset=0`）
  - 静的サイト生成（SSG）またはIncremental Static Regeneration（ISR, `revalidate: 600`）で初期HTMLを生成
  - クライアントサイドhydration用にデータを渡す
  - _Requirements: 1.1, 7.1, 7.2_

- [x] 3.2 動物一覧表示クライアントコンポーネント（AnimalListClient）を作成する
  - TanStack Query `useInfiniteQuery` でInfinite Scrolling実装（`getNextPageParam` でoffset計算）
  - URLクエリパラメータ（`useSearchParams`）でフィルタ状態を管理
  - ローディング（LoadingSpinner）、空状態（EmptyState）、エラー（ErrorBoundary）の表示制御
  - フィルタ結果総件数（`PaginationMeta.total_count`）を表示
  - _Requirements: 1.1, 1.4, 1.5, 1.6, 1.7, 3.5, 3.9, 7.5, 7.6_

- [x] 3.3 動物カードコンポーネント（AnimalCard）を作成する
  - 種別、性別、推定年齢、収容場所、カテゴリラベル（CategoryBadge）、代表画像を表示
  - Next.js `<Image>` コンポーネントで画像を最適化表示（lazy loading、WebP変換、alt属性）
  - Next.js `<Link>` で詳細ページ（`/animals/{id}`）へのルーティング
  - レスポンシブグリッド（モバイル: 1列、タブレット: 2列、デスクトップ: 3-4列）をTailwind Gridで実装
  - タッチ対応ボタンサイズ（最小44x44px）をTailwindユーティリティで確保
  - _Requirements: 1.2, 1.3, 2.1, 5.2, 5.3, 5.4, 5.5, 5.6, 6.1_

- [x] 3.4 フィルタパネルコンポーネント（FilterPanel）を作成する
  - カテゴリフィルタ（譲渡対象、迷子、すべて）、種別フィルタ（犬、猫、すべて）、性別フィルタ（男の子、女の子、不明、すべて）をドロップダウンで提供
  - 地域フィルタ（都道府県名の部分一致検索）をテキスト入力で提供（debounce 500ms）
  - フィルタ変更時にURLクエリパラメータを更新（`useRouter`, `useSearchParams`）
  - 「フィルタをクリア」ボタンで全フィルタをリセット
  - 現在適用中のフィルタ条件を視覚的に表示（選択されたフィルタをハイライト）
  - キーボードナビゲーション（Tab, Enter, Space）をサポート
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 6.2_

- [x]* 3.5 動物一覧ページのユニットテストとE2Eテストを作成する
  - AnimalCardコンポーネントのレンダリングテスト（Vitest + React Testing Library）
  - FilterPanelコンポーネントのフィルタ変更テスト
  - E2Eテスト（Playwright）: トップページアクセス → 動物一覧表示 → 「もっと見る」クリック → 追加データ表示
  - E2Eテスト（Playwright）: フィルタ選択（種別: 犬） → フィルタ結果表示 → 「フィルタをクリア」 → 全件表示
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9_

### 動物詳細ページ実装

- [x] 4. 動物詳細ページと画像ギャラリーを実装する
- [x] 4.1 動物詳細ページ（AnimalDetailPage）をServer Componentで実装する
  - `app/animals/[id]/page.tsx` で個別動物データをサーバーサイドフェッチ（`GET /animals/{id}`）
  - 存在しないIDの場合、`notFound()` 関数でNotFoundPageにリダイレクト
  - 動的ルーティングでIDパラメータの型安全性を確保（TypeScript number型）
  - _Requirements: 2.1, 2.8_

- [x] 4.2 404エラーページ（NotFoundPage）をServer Componentで実装する
  - `app/not-found.tsx` で「この動物は見つかりませんでした」というエラーページを表示
  - 「一覧に戻る」リンクをトップページ（`/`）へのNext.js `<Link>` で提供
  - _Requirements: 2.8_

- [x] 4.3 動物詳細表示クライアントコンポーネント（AnimalDetailClient）を作成する
  - カテゴリ（譲渡対象/迷子）をCategoryBadgeで目立つ位置に表示
  - 種別、性別、推定年齢、毛色、体格、収容日、収容場所、電話番号を表示
  - 「一覧に戻る」ボタンをNext.js `useRouter` で実装
  - 適切な見出し構造（h1: 動物名/種別、h2: 詳細情報セクション）を使用
  - _Requirements: 2.2, 2.3, 2.7, 6.4_

- [x] 4.4 画像ギャラリーコンポーネント（ImageGallery）を作成する
  - 全画像をギャラリー形式でNext.js `<Image>` コンポーネントで表示
  - 画像クリックでImageModal起動、拡大表示
  - キーボードナビゲーション（矢印キー）でギャラリー内移動
  - 画像alt属性を適切に設定（「{種別}の画像{index}」）
  - _Requirements: 2.4, 2.5, 6.1, 6.2_

- [x] 4.5 画像拡大モーダルコンポーネント（ImageModal）を作成する
  - 画像拡大表示、Escキーで閉じる、背景クリックで閉じる
  - モーダルをReact PortalでDOM body直下にマウント
  - ARIA属性（`role="dialog"`, `aria-modal="true"`）でアクセシビリティ確保
  - _Requirements: 2.5, 6.2_

- [x] 4.6 (P) 自治体連絡先表示コンポーネント（ContactInfo）を作成する
  - 収容場所と電話番号を目立つ位置に表示
  - 電話番号が利用可能な場合、`tel:` スキームでタップ可能リンク表示
  - カテゴリ別案内文を条件分岐で表示（譲渡対象: 「譲渡についてはお電話でお問い合わせください」、迷子: 「飼い主の方はお早めにご連絡ください」）
  - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [x] 4.7 (P) 外部リンクコンポーネント（ExternalLink）を作成する
  - 「元のページを見る」ボタンを表示し、クリック時に`source_url` を新しいタブで開く（`target="_blank"`, `rel="noopener noreferrer"`）
  - タッチ対応ボタンサイズ（最小44x44px）を確保
  - _Requirements: 2.6, 4.5, 5.5_

- [x]* 4.8 動物詳細ページのユニットテストとE2Eテストを作成する
  - AnimalDetailClientコンポーネントのレンダリングテスト
  - ImageGalleryコンポーネントの画像クリックモーダル表示テスト
  - E2Eテスト（Playwright）: 動物カードクリック → 詳細ページ遷移 → 画像ギャラリー表示 → 画像クリックで拡大
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 4.1, 4.2, 4.3, 4.4, 4.5_

### アクセシビリティとパフォーマンス検証

- [x] 5. アクセシビリティとパフォーマンスを検証・最適化する
- [x] 5.1 (P) WCAG 2.1 AA準拠のアクセシビリティテストをCI/CDに統合する
  - axe-coreでコンポーネントレベルのアクセシビリティテストを実行
  - Lighthouse CIでページレベルのアクセシビリティスコア（100点満点）を検証
  - キーボードナビゲーションテスト（Tab, Enter, Space, Arrow keys）をE2Eテストに含める
  - スクリーンリーダー（VoiceOver/NVDA）で主要フローの読み上げを手動確認
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

- [x] 5.2 (P) パフォーマンステストをCI/CDに統合する
  - Lighthouse CIでパフォーマンススコア（LCP 2.5秒以内、CLS 0.1以下、FID 100ms以下）を検証
  - Next.js Image WebP変換、レスポンシブ画像サイズ、lazy loading動作を確認
  - TanStack Query Stale-While-Revalidate動作確認、キャッシュヒット率測定
  - 初期ページ読み込み時間を3G回線シミュレーションで測定（3秒以内目標）
  - _Requirements: 5.6, 7.1, 7.2, 7.3, 7.4_

- [x]* 5.3 E2Eアクセシビリティテストを作成する
  - E2Eテスト（Playwright）: キーボードナビゲーション（Tab, Enter, Space）で全機能操作
  - フォーカス状態の視覚的表示確認（`:focus-visible` スタイル）
  - 見出し構造（h1〜h6）の階層確認
  - ランドマーク要素（header, nav, main, footer）の存在確認
  - _Requirements: 6.2, 6.3, 6.4, 6.6_

### 環境変数とデプロイ設定

- [x] 6. (P) 環境変数設定とVercelデプロイ準備を実施する
- [x] 6.1 (P) 環境変数ファイルを作成しAPI URLを設定する
  - `.env.local` で開発環境API URL（`API_BASE_URL=http://localhost:8000`）を設定
  - `.env.production` で本番環境API URL（Vercel環境変数で設定）を設定
  - TypeScript型定義で環境変数を型安全にアクセス（`process.env.NEXT_PUBLIC_API_BASE_URL`）
  - _Requirements: 1.1, 2.1_

- [x] 6.2 (P) Vercelデプロイ設定を構成する
  - `vercel.json` でビルド設定、環境変数、リダイレクトルールを定義
  - GitHub ActionsでCI/CD統合（Lint, Test, Lighthouse CI自動実行）
  - 本番環境でISR（Incremental Static Regeneration）を有効化（`revalidate: 600`）
  - _Requirements: 7.1, 7.2, 7.4_

## 要件カバレッジマトリクス

| Requirement | タスク | カバレッジ |
|-------------|--------|-----------|
| 1.1 | 1.2, 3.1, 3.2, 6.1 | ✅ |
| 1.2 | 1.2, 3.3, 3.5 | ✅ |
| 1.3 | 1.2, 2.2, 3.3, 3.5 | ✅ |
| 1.4 | 1.2, 3.2, 3.5 | ✅ |
| 1.5 | 1.2, 3.2, 3.5 | ✅ |
| 1.6 | 1.2, 2.4, 3.2, 3.5 | ✅ |
| 1.7 | 1.2, 3.2 | ✅ |
| 2.1 | 1.2, 3.3, 4.1, 4.8, 6.1 | ✅ |
| 2.2 | 1.2, 2.2, 4.1, 4.3, 4.8 | ✅ |
| 2.3 | 1.2, 4.3, 4.8 | ✅ |
| 2.4 | 4.4, 4.8 | ✅ |
| 2.5 | 4.4, 4.5, 4.8 | ✅ |
| 2.6 | 4.7, 4.8 | ✅ |
| 2.7 | 4.3, 4.8 | ✅ |
| 2.8 | 4.1, 4.2, 4.8 | ✅ |
| 3.1 | 1.2, 3.4, 3.5 | ✅ |
| 3.2 | 1.2, 3.4, 3.5 | ✅ |
| 3.3 | 1.2, 3.4, 3.5 | ✅ |
| 3.4 | 1.2, 3.4, 3.5 | ✅ |
| 3.5 | 1.2, 3.2, 3.4, 3.5 | ✅ |
| 3.6 | 3.4, 3.5 | ✅ |
| 3.7 | 3.4, 3.5 | ✅ |
| 3.8 | 3.4, 3.5 | ✅ |
| 3.9 | 3.2, 3.5 | ✅ |
| 4.1 | 4.6, 4.8 | ✅ |
| 4.2 | 4.6, 4.8 | ✅ |
| 4.3 | 4.6, 4.8 | ✅ |
| 4.4 | 4.6, 4.8 | ✅ |
| 4.5 | 4.7, 4.8 | ✅ |
| 4.6 | 2.1 | ✅ |
| 5.1 | 2.1 | ✅ |
| 5.2 | 3.3 | ✅ |
| 5.3 | 3.3 | ✅ |
| 5.4 | 3.3 | ✅ |
| 5.5 | 3.3, 4.7 | ✅ |
| 5.6 | 1.4, 3.3, 5.2 | ✅ |
| 6.1 | 3.3, 4.4, 5.1 | ✅ |
| 6.2 | 3.4, 4.4, 4.5, 5.1, 5.3 | ✅ |
| 6.3 | 1.3, 5.1, 5.3 | ✅ |
| 6.4 | 4.3, 5.1, 5.3 | ✅ |
| 6.5 | 1.3, 5.1 | ✅ |
| 6.6 | 2.1, 5.1, 5.3 | ✅ |
| 7.1 | 1.1, 3.1, 5.2, 6.2 | ✅ |
| 7.2 | 1.1, 3.1, 5.2, 6.2 | ✅ |
| 7.3 | 1.4, 5.2 | ✅ |
| 7.4 | 5.2, 6.2 | ✅ |
| 7.5 | 1.5, 2.3, 3.2 | ✅ |
| 7.6 | 1.5, 2.5, 3.2 | ✅ |

## 実装順序の推奨

1. **フェーズ1: 基盤構築** (タスク1.1〜1.5) — 並行実行可能
2. **フェーズ2: コアUIコンポーネント** (タスク2.1〜2.5) — 並行実行可能
3. **フェーズ3: 動物一覧ページ** (タスク3.1〜3.4) — 順次実行（3.1 → 3.2 → 3.3, 3.4は並行可能）
4. **フェーズ4: 動物詳細ページ** (タスク4.1〜4.7) — 順次実行（4.1, 4.2は並行可能、4.3〜4.7は4.1完了後に並行実行）
5. **フェーズ5: 検証・最適化** (タスク5.1〜5.2) — 並行実行可能
6. **フェーズ6: デプロイ準備** (タスク6.1〜6.2) — 並行実行可能
7. **フェーズ7: テスト** (タスク3.5, 4.8, 5.3) — オプション、MVP後に実施

## 注意事項

- **並行実行可能なタスク（(P)マーク）**: データ依存関係がなく、ファイルやリソースの競合がないタスク。フェーズごとにグループ化して並行実行を推奨。
- **オプショナルテスト（*マーク）**: MVP後に実施可能なテスト。コア機能実装を優先し、テストは段階的に追加。
- **環境変数設定**: タスク6.1を早期に実施し、開発環境でバックエンドAPIに接続可能にする。
- **アクセシビリティとパフォーマンス**: タスク5.1〜5.2をCI/CDに統合し、継続的に検証する。
