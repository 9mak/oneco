# Requirements Document

## Project Description (Input)
ロードマップ Phase 1.5「トップページ刷新（インタラクティブ日本地図 / ヒートマップ）」を実装する。

現状トップページは地方別グリッドで都道府県を表示しているが、視覚的なインパクトに欠ける。日本地図 SVG をベースにしたインタラクティブマップに刷新し、保護動物の在庫件数を都道府県ごとにヒートマップで可視化する。

### 主要要件
1. 日本地図 SVG（topojson/GeoJSON 由来）を Next.js 16 App Router 上に表示
2. 都道府県を hover で件数ポップオーバー、click でその県の動物一覧へ遷移
3. ヒートマップ濃度は件数に応じて段階化（quantile bins）、凡例も表示
4. 件数 0 の県はクリック不可（既存 a11y 対応と整合）
5. モバイル/タブレット対応（タッチで詳細表示、レスポンシブスケール）
6. SSR/SSG ファースト（初期表示は静的、件数だけ Server Component で fetch）
7. パフォーマンス: LCP 2.5s 以内、初期ペイロード 200KB 以内（SVG 圧縮 + 動的 import）
8. 既存の地方別グリッドは「地図 + リスト」併存 or 切替トグルとして残す

### データソース
既存 `/api/animals` の県別 aggregation を再利用、あるいは `/api/animals/by-prefecture` を新設。

### 技術
- 日本地図ライブラリ候補: `react-japan-map`、`d3-geo` + topojson、`@svg-japan/react`
- 候補比較は design フェーズで実施

### a11y
- キーボードフォーカスで県を選択可能
- スクリーンリーダーで「47都道府県のうち X 件保護動物がいる N 県を地図で表示」
- カラーコントラスト AA 適合（既存 [[a11y_color_contrast]] と整合）

### 副次目的
Phase 2 クラウドファンディング向けの「日本中で動いている」可視化として使う。OG 画像生成も検討。

## Requirements
<!-- Will be generated in /kiro:spec-requirements phase -->
