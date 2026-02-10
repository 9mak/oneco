# Public Web Portal - Frontend

保護動物情報を一般ユーザーに提供するWebフロントエンド

## 技術スタック

- **Framework**: Next.js 15 (App Router)
- **UI Library**: React 19
- **Language**: TypeScript 5+
- **Styling**: Tailwind CSS v4
- **State Management**: TanStack Query v5
- **Testing**: Vitest + React Testing Library
- **Deployment**: Vercel

## 開発環境セットアップ

### 前提条件

- Node.js 20以上
- npm または yarn

### インストール

```bash
npm install
```

### 環境変数設定

`.env.local.example` をコピーして `.env.local` を作成:

```bash
cp .env.local.example .env.local
```

`.env.local` でAPI URLを設定:

```
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

### 開発サーバー起動

```bash
npm run dev
```

ブラウザで [http://localhost:3000](http://localhost:3000) を開く。

## スクリプト

- `npm run dev` - 開発サーバー起動
- `npm run build` - 本番ビルド
- `npm start` - 本番サーバー起動
- `npm run lint` - ESLint実行
- `npm test` - テスト実行
- `npm run test:watch` - テストをwatchモードで実行
- `npm run test:coverage` - テストカバレッジ取得

## プロジェクト構造

```
frontend/
├── app/                    # Next.js App Router pages
│   ├── layout.tsx         # Root layout
│   ├── page.tsx           # Home page (動物一覧)
│   ├── animals/
│   │   └── [id]/
│   │       └── page.tsx   # 動物詳細ページ
│   └── not-found.tsx      # 404ページ
├── components/            # Reactコンポーネント
│   ├── animals/          # 動物関連コンポーネント
│   │   ├── AnimalCard.tsx
│   │   ├── AnimalListClient.tsx
│   │   ├── FilterPanel.tsx
│   │   ├── AnimalDetailClient.tsx
│   │   ├── ImageGallery.tsx
│   │   ├── ImageModal.tsx
│   │   ├── ContactInfo.tsx
│   │   └── ExternalLink.tsx
│   ├── layout/           # レイアウトコンポーネント
│   │   ├── Header.tsx
│   │   └── Footer.tsx
│   ├── ui/               # 共通UIコンポーネント
│   │   ├── CategoryBadge.tsx
│   │   ├── LoadingSpinner.tsx
│   │   ├── EmptyState.tsx
│   │   └── ErrorBoundary.tsx
│   └── providers/        # Context Providers
│       └── QueryProvider.tsx
├── lib/                  # ユーティリティ
│   └── queryClient.ts   # TanStack Query設定
├── types/                # TypeScript型定義
│   └── animal.ts        # APIスキーマ対応型定義
└── tests/                # テストファイル (各コンポーネントと同じディレクトリに配置)
```

## テスト

### ユニットテスト実行

```bash
npm test
```

### テストカバレッジ

```bash
npm run test:coverage
```

### テスト対象コンポーネント

- `AnimalCard` - 動物カード表示
- `FilterPanel` - フィルタリングUI
- `ImageGallery` - 画像ギャラリー
- `AnimalDetailClient` - 動物詳細表示

## デプロイ

### Vercelデプロイ

1. Vercelプロジェクトを作成
2. 環境変数を設定:
   - `NEXT_PUBLIC_API_BASE_URL`: 本番APIのURL
3. GitHubリポジトリと連携してデプロイ

### 環境変数 (Vercel)

Vercelダッシュボードで以下の環境変数を設定:

- `NEXT_PUBLIC_API_BASE_URL`: `https://your-api-domain.com`

## アクセシビリティ

本プロジェクトはWCAG 2.1 レベルAA準拠を目標としています:

- キーボードナビゲーション対応
- スクリーンリーダー対応
- 適切なコントラスト比
- セマンティックHTML

## パフォーマンス目標

- 初期ページ読み込み時間: 3秒以内 (3G回線相当)
- Largest Contentful Paint (LCP): 2.5秒以内
- Cumulative Layout Shift (CLS): 0.1以下
- First Input Delay (FID): 100ms以下

## ライセンス

このプロジェクトはMITライセンスの下で公開されています。
