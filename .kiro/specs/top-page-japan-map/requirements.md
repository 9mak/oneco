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

### a11y
- キーボードフォーカスで県を選択可能
- スクリーンリーダーで「47都道府県のうち X 件保護動物がいる N 県を地図で表示」
- カラーコントラスト AA 適合

## Introduction

Top Page Japan Map は、oneco トップページに表示する日本全国の保護動物分布を可視化するインタラクティブマップ機能です。現状の地方別グリッド表示を補完する形で、47 都道府県の在庫件数をヒートマップで一目に把握できるようにし、ユーザーが「自分の地域に保護動物がどれくらいいるか」を直感的に理解できるようにします。

副次目的として、Phase 2 クラウドファンディング向けの「日本中で動いている」可視化として活用します。

### 関連スペック・前提

- 既存スペック `public-web-portal` を拡張する形で実装
- 既存 API `/api/animals` の県別 aggregation を再利用、必要に応じて `/api/animals/by-prefecture` を新設
- 既存 a11y AA 適合（PR #5 マージ済）と整合する配色・操作性を維持

## Requirements

### Requirement 1: 日本地図 SVG の表示

**Objective:** As a 一般ユーザー, I want トップページで日本全国の保護動物分布を地図で見たい, so that 全国規模の活動状況を直感的に把握できる

#### Acceptance Criteria

1. When ユーザーがトップページにアクセスした, the Web Portal shall 日本地図 SVG を画面上部に表示する
2. The Web Portal shall 47 都道府県を個別の SVG パスとして描画する
3. The Web Portal shall SVG を topojson または GeoJSON 由来のデータから生成し、初期ペイロード総量を 200KB 以内に保つ
4. The Web Portal shall 地図描画コンポーネントを動的 import（next/dynamic）で遅延ロードし、LCP に影響を与えない
5. The Web Portal shall 地図表示の LCP を 2.5 秒以内、CLS を 0.1 以下に維持する
6. The Web Portal shall 既存の地方別グリッドを地図の下に併存表示する

### Requirement 2: 都道府県別ヒートマップ

**Objective:** As a 一般ユーザー, I want 都道府県ごとの保護動物件数を視覚的に区別したい, so that どの地域に多くいるか一目で分かる

#### Acceptance Criteria

1. The Web Portal shall 都道府県ごとの「保護動物件数」を quantile bins（5 段階）でヒートマップ表示する
2. The Web Portal shall ヒートマップの配色を WCAG 2.1 AA 基準のコントラスト比で設計し、隣接する段階を視覚的に区別可能とする
3. The Web Portal shall 件数 0 の都道府県を中立色（ヒートマップ外）で塗り、件数の有無を一目で識別できるようにする
4. The Web Portal shall 地図の凡例（legend）を地図の右下または下部に表示し、各段階の件数レンジを明示する
5. The Backend API shall `/api/animals/by-prefecture` で 47 都道府県の件数集計を返却する
6. The Web Portal shall 件数データを Server Component（fetch）で取得し、CSR ハイドレーション前から表示可能にする

### Requirement 3: ホバーとクリックインタラクション

**Objective:** As a 一般ユーザー, I want 気になる県の詳細をホバー / クリックで確認したい, so that 一覧ページに最短で遷移できる

#### Acceptance Criteria

1. When ユーザーがマウスで都道府県をホバーした, the Web Portal shall ポップオーバー（tooltip）でその県名と件数を表示する
2. When ユーザーがタッチデバイスで都道府県をタップした, the Web Portal shall ポップオーバーをタッチ位置近傍に表示する
3. When ユーザーが件数 1 以上の都道府県をクリックした, the Web Portal shall その県でフィルタされた動物一覧ページ（`/animals?prefecture={県名}`）へ遷移する
4. If 都道府県の件数が 0, then the Web Portal shall その都道府県をクリック不可にし、ポインタを `not-allowed` カーソルに変更する
5. The Web Portal shall ホバー / フォーカス時に該当都道府県のパスを視覚的にハイライト（aria-current 相当）する

### Requirement 4: キーボードアクセシビリティ

**Objective:** As a スクリーンリーダー / キーボード利用者, I want 地図上の都道府県をキーボードで選択したい, so that マウスなしでも全機能を利用できる

#### Acceptance Criteria

1. The Web Portal shall 地図上の各都道府県（件数 1 以上のもの）に Tab フォーカス可能な属性を付与する
2. When ユーザーがキーボードフォーカスを都道府県に移した, the Web Portal shall フォーカスインジケータ（4.5:1 以上のコントラスト）を表示する
3. When ユーザーがフォーカス中の都道府県で Enter / Space を押下した, the Web Portal shall その県の動物一覧ページへ遷移する
4. The Web Portal shall 地図全体に `aria-label="47 都道府県のうち N 県で X 件の保護動物を地図表示"` を設定する
5. The Web Portal shall 各都道府県の SVG path に `aria-label="{県名}: {件数}件"` を設定する
6. The Web Portal shall 地図と等価な情報を持つ data table（隠し非表示でも可）を提供し、screen reader で全件アクセスできるようにする

### Requirement 5: レスポンシブとモバイル対応

**Objective:** As a モバイルユーザー, I want スマートフォンでも快適に地図を操作したい, so that 移動中でも保護動物分布を確認できる

#### Acceptance Criteria

1. The Web Portal shall 地図 SVG を viewBox ベースでスケーラブルにし、ブレークポイント `lg`（1024px）以上で幅 800px、`md`（768px）で 600px、それ未満で画面幅 100% に縮小する
2. When 画面幅が 640px 未満, the Web Portal shall タッチターゲットを最小 44x44 CSS px で確保する
3. When 画面幅が 640px 未満, the Web Portal shall 地図の代わりに「47 都道府県リスト + ヒートマップ凡例」のフォールバック UI を表示するオプションをユーザーに提供する
4. The Web Portal shall ピンチズーム操作で地図を拡大/縮小可能にする
5. The Web Portal shall 横向き / 縦向きの切り替えでレイアウト崩れを起こさない

### Requirement 6: 切替トグル（地図 / リスト）

**Objective:** As a 一般ユーザー, I want 地図表示とリスト表示を切り替えたい, so that 自分の好みに合った見方を選べる

#### Acceptance Criteria

1. The Web Portal shall トップページ上部に「地図」「リスト」切替トグルを表示する
2. When ユーザーがトグルを切り替えた, the Web Portal shall 表示モードを切り替え、選択状態を localStorage または cookie に保存する
3. When ユーザーが次回トップページにアクセスした, the Web Portal shall 前回選択した表示モードで初期表示する
4. The Web Portal shall 初回訪問時のデフォルトを「地図」にする

### Requirement 7: パフォーマンスと SEO

**Objective:** As a プロダクトオーナー, I want トップページが検索エンジンに正しく評価されて欲しい, so that オーガニック流入が落ちない

#### Acceptance Criteria

1. The Web Portal shall 地図の都道府県件数を Server Component で fetch し、初期 HTML に文字列として含める
2. The Web Portal shall metadata API で `og:image` を生成し、SNS シェア時のサムネイルとして利用できる
3. The Web Portal shall Lighthouse Performance スコアを 80 点以上に保つ
4. The Web Portal shall Lighthouse Accessibility スコアを 100 点に保つ
5. The Web Portal shall 地図描画失敗時（JS 無効 / SVG 読み込み失敗）にも既存の地方別グリッドが表示される（progressive enhancement）

### Requirement 8: テストと a11y 検証

**Objective:** As a 開発者, I want 地図機能を継続的に検証したい, so that 後続変更で a11y や機能が壊れない

#### Acceptance Criteria

1. The Web Portal shall E2E a11y テスト（@axe-core/playwright）で WCAG 2.1 AA 基準を 0 violation でクリアする
2. The Web Portal shall 地図コンポーネントのユニットテスト（vitest）でホバー / クリック / フォーカスの挙動を検証する
3. The Web Portal shall 視覚回帰テスト（既存基盤があれば）で地図描画のスクリーンショットを保存し、後続変更時に差分検出可能にする
4. When 件数 API が 5xx エラーを返した, the Web Portal shall 「全国マップを読み込めませんでした」と表示し、既存の地方別グリッドのみで動作継続する
