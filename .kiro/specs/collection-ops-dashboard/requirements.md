# Requirements Document

## Project Description (Input)
ロードマップ Phase 1.5 の「収集オペレーション可視化ダッシュボード」を実装する。`/admin` 配下に認証ゲート付きでダッシュボードを設置し、運用者がデータ収集の健全性を一目で把握できるようにする。

### 主要パネル
1. サイト別 直近実行ステータス（成功/失敗/スキップ + 最終実行時刻）
2. 県別件数の時系列推移
3. LLM 利用コスト累計（Groq / Anthropic 別）
4. 抽出失敗ランキング（Top 10 サイト）
5. sites.yaml の全 209 サイト一覧と次回実行予定

### データソース
- 既存 PostgreSQL（Supabase）
- `output/animals.json` / `snapshots/latest.json`
- GitHub Actions API（ワークフロー実行履歴）

### 技術スタック
- フロント: Next.js 16 App Router + Tailwind、Recharts でグラフ描画
- バックエンド: FastAPI に `/api/admin/...` を追加

### SLO
- 操作レイテンシ 2s 以内
- 自動更新 30s

### 副次目的
Phase 2 のクラウドファンディング時に「実績ある」と見せる説得材料も兼ねるため、公開可能なメトリクス（累計件数、対応自治体数）は別 URL で OG 画像も出せる構成にしておく。

## Introduction

Collection Ops Dashboard は、oneco の全国 209+ サイト収集パイプラインの健全性を運用者が一目で把握するための管理画面です。これまで GitHub Actions のログを開いて初めて分かっていた失敗状況・データ量・LLM コストを、`/admin` 配下の単一画面に集約します。

副次目的として、Phase 2 のクラウドファンディング時に「実績」として外部に見せられる公開メトリクス画面（OG 画像対応）を派生形で提供します。

### 関連スペック・前提

- 既存スペック `data-collector`, `animal-api-persistence`, `animal-repository`, `public-web-portal` に依存
- 既存の PostgreSQL（Supabase）、`output/animals.json`、`snapshots/latest.json`、GitHub Actions API を参照
- Next.js 16 App Router フロントエンドと FastAPI バックエンドに新規ルートを追加

## Requirements

### Requirement 1: 管理画面の認証ゲート

**Objective:** As a oneco 運用者, I want `/admin` 配下に第三者がアクセスできないようにしたい, so that 内部運用情報（収集失敗・コスト等）が外部に漏れない

#### Acceptance Criteria

1. When 未認証ユーザーが `/admin` 配下の URL にアクセスした, the Web Portal shall ログイン画面または 401 ステータスへリダイレクトする
2. When 認証済みユーザーが `/admin` 配下にアクセスした, the Web Portal shall ダッシュボード本体を表示する
3. The Web Portal shall 認証セッションを HTTPOnly Cookie で保持する
4. The Web Portal shall 認証ロジックを Next.js Middleware で実装し、Server Component より前に判定する
5. If 認証セッションが有効期限切れ, then the Web Portal shall ログイン画面へリダイレクトする
6. The Backend API shall `/api/admin/*` 全てのエンドポイントで認証トークンを検証し、未認証リクエストには 401 を返す

### Requirement 2: サイト別 直近実行ステータスパネル

**Objective:** As a 運用者, I want 全サイトの直近の収集結果を一覧で確認したい, so that どのサイトが落ちているかをすぐに特定できる

#### Acceptance Criteria

1. The Dashboard shall sites.yaml に登録された全サイトについて、直近実行の結果（成功 / 失敗 / スキップ / 未実行）を一覧表示する
2. The Dashboard shall 各サイト行に「最終実行時刻」「収集件数」「処理時間」「直近のエラーメッセージ（あれば）」を表示する
3. When 運用者がサイト行をクリックした, the Dashboard shall そのサイトの過去 7 日間の実行履歴ドリルダウンを表示する
4. The Dashboard shall 失敗ステータスのサイトを画面上部にまとめてピン留めする
5. When 直近実行から 36 時間以上経過したサイトが存在する, the Dashboard shall 警告アイコンと共に「Stale」と表示する
6. The Backend API shall `/api/admin/sites/status` で全サイトの最新ステータスを JSON で返却する

### Requirement 3: 県別件数の時系列推移パネル

**Objective:** As a 運用者, I want 各都道府県の保護動物件数の推移を確認したい, so that 急増・急減などの異常を発見できる

#### Acceptance Criteria

1. The Dashboard shall 47 都道府県それぞれの「保護動物件数」の過去 30 日間の時系列推移を折れ線グラフで表示する
2. The Dashboard shall 「全国合計」「地方別」「都道府県別」の集計粒度切替を提供する
3. When 運用者が期間切替（7d / 30d / 90d / 全期間）を選択した, the Dashboard shall 選択された期間のデータでグラフを再描画する
4. If ある都道府県の件数が前日比で 50% 以上変動した, then the Dashboard shall その都道府県名を「異常検知」セクションに表示する
5. The Backend API shall `/api/admin/animals/timeseries?prefecture=&from=&to=` で時系列データを返却する
6. The Backend API shall 日次集計を `animals_daily_aggregate` ビュー（または同等のクエリ）から読み出す

### Requirement 4: LLM 利用コスト累計パネル

**Objective:** As a 運用者, I want LLM プロバイダー別の利用コストを累積で把握したい, so that 予算管理と無料枠到達前のアラートができる

#### Acceptance Criteria

1. The Dashboard shall Groq / Anthropic それぞれの「累計トークン消費」「累計推定コスト（USD）」を表示する
2. The Dashboard shall 当日・当月・全期間の集計粒度切替を提供する
3. When Groq の当日トークン消費が 80,000 トークンを超えた, the Dashboard shall 警告バナーを表示する
4. If 当日トークン消費が日次上限 100,000 トークンに到達, then the Dashboard shall Critical レベルの警告を表示する
5. The Backend API shall `/api/admin/llm/usage` で プロバイダー別の累計使用量を返却する
6. The Data Collector shall 各 LLM 呼び出しごとに「provider, model, prompt_tokens, completion_tokens, cost_usd」を `llm_usage_logs` テーブルへ記録する

### Requirement 5: 抽出失敗ランキングパネル

**Objective:** As a 運用者, I want 直近で最も収集失敗が多いサイトを把握したい, so that 修正の優先順位を決められる

#### Acceptance Criteria

1. The Dashboard shall 過去 7 日間で失敗回数が多いサイト Top 10 をランキング表示する
2. The Dashboard shall 各サイト行に「失敗回数」「失敗率（試行に対する）」「主な失敗理由カテゴリ（rate_limit / parse_error / network / timeout / other）」を表示する
3. When 運用者がランキング行をクリックした, the Dashboard shall そのサイトの失敗ログ詳細（直近 10 件）を表示する
4. The Backend API shall `/api/admin/sites/failure-ranking?days=7&limit=10` で集計データを返却する
5. The Data Collector shall 各サイト処理結果（成功/失敗/失敗理由カテゴリ）を `site_run_logs` テーブルへ記録する

### Requirement 6: 全サイト一覧と次回実行予定

**Objective:** As a 運用者, I want sites.yaml に登録された全 209+ サイトの構成を確認したい, so that 設定の見落としや次回実行時刻を把握できる

#### Acceptance Criteria

1. The Dashboard shall sites.yaml に登録された全サイトを表で表示する
2. The Dashboard shall 各サイト行に「サイト名」「都道府県」「extraction（llm/rule）」「requires_js」「最終収集件数」を表示する
3. The Dashboard shall 「次回実行予定時刻」を GitHub Actions schedule (cron) から算出して表示する
4. When 運用者が検索ボックスに県名やサイト名を入力した, the Dashboard shall インクリメンタルにフィルタリングして表示する
5. The Backend API shall `/api/admin/sites` で sites.yaml の構造をパース済 JSON として返却する

### Requirement 7: 自動更新とパフォーマンス SLO

**Objective:** As a 運用者, I want ダッシュボードが常に最新状態を反映してほしい, so that 別途リロード操作なしに状況把握できる

#### Acceptance Criteria

1. The Dashboard shall 30 秒ごとに全パネルのデータを自動更新する
2. The Dashboard shall 自動更新の有効/無効を切り替えるトグルを画面右上に表示する
3. The Dashboard shall ユーザー操作（フィルタ切替、ドリルダウン展開等）に対して 2 秒以内に描画完了する
4. When 自動更新中, the Dashboard shall 「最終更新時刻」表示と更新中インジケータを表示する
5. If API 呼び出しが 5 秒以内に応答しない, then the Dashboard shall タイムアウト警告を表示し、前回データを保持する
6. The Backend API shall `/api/admin/*` の P95 レスポンスタイムを 1 秒以内に収める

### Requirement 8: 公開メトリクス（クラファン用）

**Objective:** As a プロダクトオーナー, I want 認証不要の公開メトリクスページを別途持ちたい, so that クラウドファンディングや SNS でプロジェクト実績を訴求できる

#### Acceptance Criteria

1. The Web Portal shall `/stats`（または同等の公開 URL）で認証不要の公開メトリクスページを提供する
2. The Public Stats Page shall 「累計掲載動物数」「対応自治体（県・市）数」「対応サイト数」「平均譲渡待機日数（取得可能なら）」を表示する
3. The Public Stats Page shall 内部運用情報（コスト / 失敗ログ / サイト固有のエラー）を一切表示しない
4. The Public Stats Page shall OG 画像 (`/stats/og.png`) を動的生成し、SNS でシェアした際のサムネイルとして利用できる
5. The Backend API shall `/api/public/stats` で公開メトリクスを返却する（CORS 許可、認証不要）
6. The Public Stats Page shall LCP 2.5 秒以内、CLS 0.1 以下を保つ

### Requirement 9: アクセシビリティとレスポンシブ

**Objective:** As a 運用者, I want ダッシュボードを PC・タブレットで快適に使いたい, so that 移動中や別環境でも状況確認できる

#### Acceptance Criteria

1. The Dashboard shall 既存 public-web-portal と同じく WCAG 2.1 AA 適合のカラーコントラスト比を保つ
2. The Dashboard shall ブレークポイント `lg`（1024px）以上で 3 カラムレイアウト、`md`（768px）で 2 カラム、それ未満で 1 カラムに切り替える
3. The Dashboard shall 全てのインタラクティブ要素にキーボードフォーカスインジケータを表示する
4. The Dashboard shall グラフコンポーネントに data table としての等価表現（screen reader 向け）を提供する
5. The Dashboard shall E2E a11y テスト（@axe-core/playwright）に 0 violation で通過する

### Requirement 10: 観測可能性とエラーハンドリング

**Objective:** As a 運用者, I want ダッシュボード自体の不具合も観測したい, so that ダッシュボード経由で本番状況を見落とさない

#### Acceptance Criteria

1. The Backend API shall `/api/admin/*` の全エラーを構造化ログ（JSON）で出力する
2. When Backend API が 5xx を返した, the Dashboard shall パネル単位でエラーバナーを表示し、他パネルの動作は継続する
3. The Dashboard shall API 接続不可時、最後に取得したデータをローカルキャッシュから表示する（stale-while-revalidate）
4. The Backend API shall サーバ側で計測したパネル別の取得失敗率を `/api/admin/_health` で返却する
5. If 直近 24 時間で `/api/admin/*` のエラー率が 10% を超えた, then the Backend API shall NotificationClient 経由で Slack に WARNING を送信する
