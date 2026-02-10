# Requirements Document

## Project Description (Input)
public-web-portal: 保護動物情報を一般ユーザーに提供するWebフロントエンド。動物一覧・詳細表示、検索フィルタ（種別、年齢、地域、カテゴリ）、自治体連絡先への誘導、レスポンシブデザイン。

## Introduction

Public Web Portal は、保護動物情報を一般ユーザーに分かりやすく提供するWebフロントエンドです。

### データソースについて

本システムは、各都道府県の動物愛護センターサイトからデータを収集します。現在は高知県（高知県中央・中村小動物管理センター: https://kochi-apc.com）を第1対象としており、今後他の都道府県（北海道など）へアダプターパターンで拡張予定です。

収集するデータは以下の2カテゴリに分類されます：
- **譲渡対象**: 新しい飼い主を探している動物
- **迷子**: 飼い主の迎えを待つ動物（迷子として保護された動物）

### 依存関係

本機能は以下のバックエンドAPIに依存します：
- `GET /animals` - 動物一覧取得（フィルタリング、ページネーション対応）
- `GET /animals/{id}` - 動物詳細取得

**注意**: 現在のAPIには `category` フィールド（譲渡/迷子の区別）が存在しません。本要件の実装に先立ち、data-collector および animal-api-persistence の拡張が必要です。

## Requirements

### Requirement 1: 動物一覧表示

**Objective:** As a 一般ユーザー, I want 保護動物の一覧を閲覧したい, so that 現在収容されている動物を把握し、興味のある動物を見つけられる

#### Acceptance Criteria

1. When ユーザーがトップページにアクセスした, the Web Portal shall 動物一覧を表示する
2. The Web Portal shall 各動物カードに種別、性別、推定年齢、収容場所、カテゴリ（譲渡対象/迷子）、代表画像を表示する
3. The Web Portal shall カテゴリに応じたラベル（「譲渡対象」「迷子」）を動物カードに表示する
4. The Web Portal shall ページネーション機能を提供し、1ページあたり最大20件の動物を表示する
5. When ユーザーが「もっと見る」ボタンをクリックした, the Web Portal shall 次のページの動物データを読み込んで表示に追加する
6. When 動物データが存在しない, the Web Portal shall 「現在表示できる動物がいません」というメッセージを表示する
7. The Web Portal shall 収容日の新しい順（降順）で動物を表示する

### Requirement 2: 動物詳細表示

**Objective:** As a 一般ユーザー, I want 特定の動物の詳細情報を確認したい, so that 譲渡検討や飼い主への連絡前に動物の特徴を十分に把握できる

#### Acceptance Criteria

1. When ユーザーが一覧から動物カードをクリックした, the Web Portal shall その動物の詳細ページに遷移する
2. The Web Portal shall 詳細ページにカテゴリ（譲渡対象/迷子）を目立つ位置に表示する
3. The Web Portal shall 詳細ページに種別、性別、推定年齢、毛色、体格、収容日、収容場所、電話番号を表示する
4. The Web Portal shall 詳細ページに全ての画像をギャラリー形式で表示する
5. When 画像がクリックされた, the Web Portal shall 画像を拡大表示する
6. The Web Portal shall 詳細ページに「元のページを見る」リンク（source_url）を表示する
7. The Web Portal shall 詳細ページに「一覧に戻る」ナビゲーションを表示する
8. If 指定されたIDの動物が存在しない, then the Web Portal shall 「この動物は見つかりませんでした」というエラーページを表示する

### Requirement 3: 検索・フィルタリング機能

**Objective:** As a 一般ユーザー, I want 条件を指定して動物を絞り込みたい, so that 自分の希望に合った動物を効率的に見つけられる

#### Acceptance Criteria

1. The Web Portal shall カテゴリフィルタ（譲渡対象、迷子、すべて）を提供する
2. The Web Portal shall 種別フィルタ（犬、猫、すべて）を提供する
3. The Web Portal shall 性別フィルタ（男の子、女の子、不明、すべて）を提供する
4. The Web Portal shall 地域フィルタ（都道府県名の部分一致検索）を提供する
5. When ユーザーがフィルタ条件を変更した, the Web Portal shall フィルタに合致する動物のみを表示する
6. When 複数のフィルタが選択された, the Web Portal shall すべての条件を満たす動物のみを表示する（AND条件）
7. The Web Portal shall 現在適用中のフィルタ条件を視覚的に表示する
8. When ユーザーが「フィルタをクリア」ボタンをクリックした, the Web Portal shall すべてのフィルタを解除して全件表示に戻る
9. The Web Portal shall フィルタ結果の総件数を表示する

### Requirement 4: 自治体連絡先への誘導

**Objective:** As a 一般ユーザー, I want 動物について問い合わせる方法を知りたい, so that 譲渡希望や迷子の飼い主として自治体に連絡できる

#### Acceptance Criteria

1. The Web Portal shall 詳細ページに収容場所と電話番号を目立つ位置に表示する
2. Where 電話番号が利用可能, the Web Portal shall 電話番号をタップ可能なリンク（tel:）として表示する
3. While カテゴリが「譲渡対象」の場合, the Web Portal shall 「譲渡についてはお電話でお問い合わせください」という案内を表示する
4. While カテゴリが「迷子」の場合, the Web Portal shall 「飼い主の方はお早めにご連絡ください」という案内を表示する
5. The Web Portal shall 詳細ページに「元のページを見る」ボタンを表示し、クリック時に自治体の元ページ（source_url）を新しいタブで開く
6. The Web Portal shall フッターに利用規約と免責事項（情報の正確性は自治体サイトを参照）を表示する

### Requirement 5: レスポンシブデザイン

**Objective:** As a 一般ユーザー, I want スマートフォンやタブレットからも快適に閲覧したい, so that 外出先でも動物情報を確認できる

#### Acceptance Criteria

1. The Web Portal shall モバイル（〜767px）、タブレット（768px〜1023px）、デスクトップ（1024px〜）の3つのブレークポイントに対応する
2. While モバイルビューで表示中, the Web Portal shall 動物カードを1列で表示する
3. While タブレットビューで表示中, the Web Portal shall 動物カードを2列で表示する
4. While デスクトップビューで表示中, the Web Portal shall 動物カードを3〜4列で表示する
5. The Web Portal shall タッチ操作に適したボタンサイズ（最小44x44ピクセル）を確保する
6. The Web Portal shall 画像を遅延読み込み（lazy loading）し、モバイル回線での表示を最適化する

### Requirement 6: アクセシビリティ

**Objective:** As a 視覚・運動機能に制限のあるユーザー, I want アクセシブルなインターフェースを利用したい, so that 支援技術を使用しても情報にアクセスできる

#### Acceptance Criteria

1. The Web Portal shall すべての画像に代替テキスト（alt属性）を設定する
2. The Web Portal shall キーボードナビゲーションをサポートし、タブキーで全ての操作可能な要素にフォーカスできる
3. The Web Portal shall フォーカス状態を視覚的に明示する（アウトラインまたはハイライト）
4. The Web Portal shall 適切な見出し構造（h1〜h6）を使用し、スクリーンリーダーでのナビゲーションを支援する
5. The Web Portal shall WCAG 2.1 レベルAA のコントラスト比（4.5:1以上）を満たす配色を使用する
6. The Web Portal shall ランドマーク要素（header, nav, main, footer）を使用してページ構造を明確にする

### Requirement 7: パフォーマンス

**Objective:** As a 一般ユーザー, I want ページを素早く読み込みたい, so that ストレスなく動物情報を閲覧できる

#### Acceptance Criteria

1. The Web Portal shall 初期ページ読み込み時間を3秒以内（3G回線相当）に抑える
2. The Web Portal shall Largest Contentful Paint（LCP）を2.5秒以内に達成する
3. The Web Portal shall 画像を最適化された形式（WebP優先、JPEG/PNGフォールバック）で配信する
4. The Web Portal shall 静的アセット（CSS、JavaScript、画像）にキャッシュヘッダーを設定する
5. When APIからデータを取得中, the Web Portal shall ローディングインジケーターを表示する
6. If API接続エラーが発生した, then the Web Portal shall ユーザーフレンドリーなエラーメッセージと「再試行」ボタンを表示する

---

## 前提条件・依存関係

### 必要なバックエンド拡張

本要件を実装するには、以下のバックエンド拡張が先行して必要です：

1. **data-collector の拡張**
   - `RawAnimalData` に `category` フィールド追加（収集元URLから判定: `/jouto/` → "譲渡", `/maigo/` → "迷子"）
   - `AnimalData` に `category` フィールド追加

2. **animal-api-persistence の拡張**
   - `Animal` テーブルに `category` カラム追加
   - `GET /animals` エンドポイントに `category` フィルタパラメータ追加
   - `AnimalPublic` スキーマに `category` フィールド追加

### 複数都道府県対応

現在は高知県のみ対応していますが、アダプターパターンにより他の都道府県（北海道、愛媛県など）も同様の構造で追加可能です。Web Portal は `location` フィルタで地域絞り込みを提供し、複数都道府県のデータを統一的に表示します。

