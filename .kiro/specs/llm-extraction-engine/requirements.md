# Requirements Document

## Introduction

本仕様は、LLMベースの汎用データ抽出エンジンを定義する。現在の高知県アダプター（450行+特別ルール4つのルールベース実装）に代わり、Claude APIを使ってHTML→構造化データ（RawAnimalData）の抽出を汎用的に行う仕組みを構築する。YAML設定ファイルで新規サイトを追加可能にし、四国4県（徳島・香川・高松・愛媛・松山）を最初の適用先とする。将来的に全国100+サイトへスケールできる基盤とする。

## Requirements

### Requirement 1: YAML設定によるサイト定義

**Objective:** 開発者として、新規自治体サイトをYAML設定ファイルの数行追加だけで対応したい。サイトごとにアダプターコードを書かずに済むようにするため。

#### Acceptance Criteria
1. The LLM Extraction Engine shall YAMLファイルからサイト定義（名前、都道府県、一覧ページURL、リンクパターン、抽出方式）を読み込む
2. When 新しいサイト定義がYAMLに追加された場合, the LLM Extraction Engine shall コード変更なしで当該サイトからのデータ収集を開始できる
3. The LLM Extraction Engine shall 各サイト定義に対して必須フィールド（name, prefecture, list_url）のバリデーションを行う
4. If YAML設定にバリデーションエラーがある場合, the LLM Extraction Engine shall 具体的なエラー箇所とメッセージを出力して起動を中断する
5. The LLM Extraction Engine shall 四国4県の以下のサイト定義を初期設定として含む:
   - 徳島県（douai-tokushima.com）
   - 香川県（pref.kagawa.lg.jp）
   - 高松市（city.takamatsu.kagawa.jp）
   - 愛媛県（pref.ehime.jp）
   - 松山市（city.matsuyama.ehime.jp）

### Requirement 2: 一覧ページからの動物詳細URLの収集

**Objective:** システムとして、各自治体サイトの一覧ページから保護動物の詳細ページURLを自動収集したい。サイトごとに異なるHTML構造に対応するため。

#### Acceptance Criteria
1. When サイト定義にlist_urlが指定されている場合, the LLM Extraction Engine shall 当該URLにアクセスし、動物詳細ページへのリンクを抽出する
2. Where サイト定義にlist_link_patternが指定されている場合, the LLM Extraction Engine shall 当該CSSセレクターを使ってリンクを絞り込む
3. Where サイト定義にlist_link_patternが指定されていない場合, the LLM Extraction Engine shall LLMを使ってページ内から動物詳細リンクを推定する
4. The LLM Extraction Engine shall 抽出した全URLを絶対URLに正規化し、重複を排除する
5. When 一覧ページにページネーションが存在する場合, the LLM Extraction Engine shall 全ページを巡回して詳細URLを収集する
6. If 一覧ページへのアクセスに失敗した場合, the LLM Extraction Engine shall エラーをログに記録し、他のサイトの処理を継続する

### Requirement 3: LLMによる動物情報の構造化抽出

**Objective:** システムとして、任意の自治体サイトの詳細ページHTMLからRawAnimalDataスキーマに準拠した構造化データを抽出したい。サイトごとのパーサー実装を不要にするため。

#### Acceptance Criteria
1. When 動物詳細ページのHTMLが渡された場合, the LLM Extraction Engine shall Claude APIを使ってRawAnimalDataの全フィールド（species, sex, age, color, size, shelter_date, location, phone, image_urls, source_url, category）を抽出する
2. The LLM Extraction Engine shall Claude APIのStructured Output（JSON Schema）を使って型安全な抽出結果を取得する
3. The LLM Extraction Engine shall 抽出時にLLMに対して動物種別（犬/猫）の文脈判定を行わせる（品種名「雑種」等から犬猫を推定）
4. The LLM Extraction Engine shall 抽出時にLLMに対して年齢テキスト（「高齢」「成犬」「生年月日：R1.5/19」等）を推定月齢に変換させる
5. The LLM Extraction Engine shall 抽出時にLLMに対して日付テキスト（令和表記、年なし日付等）をISO 8601形式に変換させる
6. The LLM Extraction Engine shall 画像URLを抽出する際、テンプレート画像（サイトUI要素）と動物写真を区別させる
7. If LLM APIの呼び出しに失敗した場合, the LLM Extraction Engine shall リトライ（最大3回、指数バックオフ）を行う
8. If リトライ後もAPI呼び出しに失敗した場合, the LLM Extraction Engine shall エラーをログに記録し、当該ページをスキップして処理を継続する

### Requirement 4: 既存パイプラインとの統合

**Objective:** システムとして、LLM抽出エンジンの出力を既存のDataNormalizer→AnimalData→AnimalRepository パイプラインに接続したい。既存のDB・API・フロントエンドを変更せずに動作させるため。

#### Acceptance Criteria
1. The LLM Extraction Engine shall MunicipalityAdapterと同じインターフェース（fetch_animal_list, extract_animal_details, normalize）を実装する
2. The LLM Extraction Engine shall 抽出結果をRawAnimalDataモデルとして出力し、既存のDataNormalizerで正規化可能にする
3. The LLM Extraction Engine shall 既存の高知県アダプター（KochiAdapter）と共存し、設定で抽出方式（llm/rule-based）を切り替え可能にする
4. When データ収集が完了した場合, the LLM Extraction Engine shall 既存のAnimalRepositoryを使ってデータベースに保存する
5. The LLM Extraction Engine shall 既存のスナップショット保存機能（snapshot_store）と互換性を持つ

### Requirement 5: APIコスト管理と効率化

**Objective:** 運営者として、Claude API利用料を予測可能かつ最小限に抑えたい。ボランティアベースの初期段階でランニングコストを制御するため。

#### Acceptance Criteria
1. The LLM Extraction Engine shall HTMLをLLMに送信する前に不要な要素（script, style, nav, footer等）を除去してトークン数を削減する
2. The LLM Extraction Engine shall Claude Haikuモデルをデフォルトの抽出モデルとして使用する（コスト最適化）
3. The LLM Extraction Engine shall 1回の実行あたりのAPI呼び出し回数と推定コストをログに出力する
4. Where サイト定義にmax_pagesが指定されている場合, the LLM Extraction Engine shall 当該ページ数を上限として一覧ページの巡回を制限する
5. The LLM Extraction Engine shall 前回の収集結果と比較し、変更のないページの再抽出をスキップする差分更新機能を持つ

### Requirement 6: エラー耐性と監視

**Objective:** 運営者として、複数サイトの収集状況を把握し、問題発生時に素早く対応したい。100+サイトの安定運用のため。

#### Acceptance Criteria
1. The LLM Extraction Engine shall 各サイト・各ページの収集結果（成功/失敗/スキップ）をサマリーとして出力する
2. If あるサイトでエラーが発生した場合, the LLM Extraction Engine shall 当該サイトをスキップし、他のサイトの処理を継続する
3. The LLM Extraction Engine shall 抽出結果に対してバリデーション（species, shelter_date, source_urlの必須チェック）を行い、不正データのDB保存を防ぐ
4. When 抽出結果のバリデーションに失敗した場合, the LLM Extraction Engine shall 警告をログに記録し、当該レコードをスキップする
5. The LLM Extraction Engine shall 実行ログに各サイトの処理時間、抽出件数、エラー件数を含める

### Requirement 7: 四国4県サイトへの対応

**Objective:** ユーザーとして、四国全県の保護動物情報を横断検索したい。高知県のみの現状から四国全域に拡大するため。

#### Acceptance Criteria
1. The LLM Extraction Engine shall 徳島県動物愛護管理センター（douai-tokushima.com）から保護動物データを抽出できる
2. The LLM Extraction Engine shall 香川県（pref.kagawa.lg.jp）の4保健所（東讃・小豆・中讃・西讃）から収容動物データを抽出できる
3. The LLM Extraction Engine shall 高松市（city.takamatsu.kagawa.jp）の「わんにゃん高松」から保護動物データを抽出できる
4. The LLM Extraction Engine shall 愛媛県動物愛護センター（pref.ehime.jp）から迷子・保護動物データを抽出できる
5. The LLM Extraction Engine shall 松山市（city.matsuyama.ehime.jp）の「はぴまるの丘」から保護動物データを抽出できる
6. The LLM Extraction Engine shall 全サイトの出典（source_url）を正確に記録し、元ページへのリンクを提供する
7. The LLM Extraction Engine shall robots.txtが存在する場合はその指示を尊重し、リクエスト間隔を最低1秒空ける

### Requirement 8: LLMプロバイダーの抽象化と差し替え

**Objective:** 運営者として、LLMプロバイダー（Anthropic/OpenAI/Google等）やモデルを設定変更のみで切り替えたい。精度・コストの状況に応じて最適なモデルを選択できるようにするため。

#### Acceptance Criteria
1. The LLM Extraction Engine shall LLMプロバイダーへのアクセスを抽象化し、統一インターフェース（プロンプト送信→構造化データ受信）を提供する
2. The LLM Extraction Engine shall YAML設定でプロバイダー（anthropic, openai, google）とモデル名を指定可能にする
3. The LLM Extraction Engine shall 初期実装としてAnthropic（Claude Haiku）をデフォルトプロバイダーとして提供する
4. The LLM Extraction Engine shall プロバイダー追加時にエンジン本体のコードを変更せず、プロバイダークラスの追加のみで対応できる設計とする
5. Where サイト定義に個別のプロバイダー/モデルが指定されている場合, the LLM Extraction Engine shall グローバル設定を上書きし、サイトごとに異なるモデルを使用できる
6. If 指定されたプロバイダーが利用不可能な場合, the LLM Extraction Engine shall エラーメッセージでサポート対象プロバイダー一覧を表示する
