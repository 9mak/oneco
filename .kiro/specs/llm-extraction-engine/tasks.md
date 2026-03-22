# Implementation Plan

- [x] 1. YAML設定の読み込みとバリデーション機能を構築する
- [x] 1.1 (P) サイト定義モデルと設定ローダーを実装する
  - サイト定義のPydanticモデルを作成し、必須フィールド（name, prefecture, list_url）のバリデーションを行う
  - グローバル設定（デフォルトプロバイダー、デフォルトモデル）とサイト別オーバーライドの解決ロジックを実装する
  - バリデーションエラー時に具体的なエラー箇所とメッセージを出力する
  - _Requirements: 1.1, 1.2, 1.3, 1.4_
  - _Contracts: SiteConfig, ExtractionConfig, SiteConfigLoader_

- [x] 1.2 (P) 設定ローダーのユニットテストを作成する
  - 正常系: 有効なYAMLの読み込みとパース
  - 異常系: 必須フィールド欠損、不正な型、未知のプロバイダー指定
  - デフォルト値（request_interval, category, extraction）の適用確認
  - サイト別オーバーライドがグローバル設定を上書きすることの確認
  - _Requirements: 1.3, 1.4, 8.5_

- [x] 2. HTML前処理によるトークン削減機能を構築する
- [x] 2.1 (P) HTML前処理エンジンを実装する
  - script, style, nav, footer, header, iframe, noscript, svg, meta, link要素の除去を実装する
  - img タグを保持して動物写真のURL抽出を可能にする
  - 相対URLから絶対URLへの変換を実装する
  - テキストの空白・改行を正規化する
  - 推定トークン数の算出機能（日本語: 文字数 × 1.5）を実装する
  - _Requirements: 5.1_
  - _Contracts: HtmlPreprocessor_

- [x] 2.2 (P) HTML前処理のユニットテストを作成する
  - 不要要素（script, style, nav等）が除去されることの確認
  - img タグが保持されることの確認
  - 相対URLが正しく絶対URLに変換されることの確認
  - トークン数推定の妥当性確認
  - _Requirements: 5.1_

- [x] 3. LLMプロバイダーの抽象化とAnthropic実装を構築する
- [x] 3.1 (P) LLMプロバイダーの抽象インターフェースを定義する
  - 動物データ抽出メソッド（HTML → 構造化データ）の抽象インターフェースを定義する
  - 詳細リンク推定メソッド（HTML → URLリスト）の抽象インターフェースを定義する
  - 抽出結果モデル（フィールド辞書 + トークン使用量）を定義する
  - サポート対象プロバイダー一覧の管理と、未対応プロバイダー指定時のエラーメッセージを実装する
  - _Requirements: 8.1, 8.4, 8.6_
  - _Contracts: LlmProvider ABC, ExtractionResult_

- [x] 3.2 Anthropic Claude APIを使った構造化抽出プロバイダーを実装する
  - tool_useとstrict modeを使ったRawAnimalDataスキーマ準拠の構造化抽出を実装する
  - 抽出プロンプトに動物種別判定（品種名からの犬猫推定）、年齢テキスト変換、日付形式変換、画像フィルタ指示を含める
  - tool_choiceで強制ツール呼び出しを設定し、レスポンスからinputフィールドを取得する
  - リトライ機能（最大3回、指数バックオフ: 1s, 2s, 4s）を実装する
  - APIキーは環境変数（ANTHROPIC_API_KEY）からの読み込みをデフォルトとする
  - デフォルトモデルとしてClaude Haikuを使用する
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 5.2, 8.3_
  - _Contracts: AnthropicProvider_

- [x] 3.3 詳細リンクのLLM推定機能を実装する
  - 一覧ページHTMLからLLMを使って動物詳細ページへのリンクを推定する機能を実装する
  - CSSセレクターが未指定のサイトに対するフォールバック抽出として機能する
  - _Requirements: 2.3, 8.1_

- [x] 3.4 (P) Anthropicプロバイダーのユニットテストを作成する
  - tool_useリクエスト構築の正確性テスト（スキーマ定義、tool_choice設定）
  - レスポンスパースの正確性テスト（構造化データ抽出、トークン数取得）
  - リトライ動作テスト（RateLimitError、APIStatusErrorでのバックオフ）
  - API呼び出しはモックを使用する
  - _Requirements: 3.1, 3.2, 3.7, 8.3_

- [x] 4. LlmAdapterの中核機能を構築する
- [x] 4.1 一覧ページからの動物詳細URL収集機能を実装する
  - サイト定義のlist_urlにアクセスし、詳細ページへのリンクを抽出する
  - CSSセレクター（list_link_pattern）が指定されている場合はそれでリンクを絞り込む
  - CSSセレクターが未指定の場合はLlmProviderのリンク推定機能にフォールバックする
  - 抽出した全URLを絶対URLに正規化し、重複を排除する
  - ページネーションの巡回（全ページ、max_pagesで制限可能）を実装する
  - リクエスト間隔の制御（最低1秒）を実装する
  - アクセス失敗時のエラーログ記録と処理継続を実装する
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 7.7_

- [x] 4.2 詳細ページからのLLM構造化抽出機能を実装する
  - 詳細ページHTMLを取得し、HtmlPreprocessorで前処理する
  - 前処理済みHTMLをLlmProviderに渡して構造化データを抽出する
  - 抽出結果をRawAnimalDataモデルとして構築する
  - API呼び出し失敗時のリトライ後スキップとエラーログを実装する
  - _Requirements: 3.1, 3.6, 3.8, 4.2_

- [x] 4.3 MunicipalityAdapterインターフェースへの準拠を実装する
  - MunicipalityAdapter ABCを継承し、fetch_animal_list / extract_animal_details / normalize の3メソッドを実装する
  - normalizeはDataNormalizerに委譲する
  - 既存のCollectorServiceからそのまま呼び出し可能にする
  - _Requirements: 4.1, 4.2, 4.3_
  - _Contracts: LlmAdapter(MunicipalityAdapter)_

- [x] 5. コスト管理・監視・エラー耐性機能を構築する
- [x] 5.1 API呼び出しのコスト追跡と実行サマリー出力を実装する
  - 1回の実行あたりのAPI呼び出し回数、合計トークン数、推定コストをログ出力する
  - 各サイト・各ページの収集結果（成功/失敗/スキップ）のサマリーを出力する
  - 各サイトの処理時間、抽出件数、エラー件数をログに含める
  - _Requirements: 5.3, 6.1, 6.5_

- [x] 5.2 抽出結果のバリデーションを実装する
  - 抽出結果に対して必須フィールド（species, shelter_date, source_url）のチェックを行う
  - バリデーション失敗時は警告をログに記録し、当該レコードをスキップする
  - 不正データのDB保存を防止する
  - _Requirements: 6.3, 6.4_

- [ ] 5.3 差分更新（変更なしページのスキップ）機能を実装する
  - 前回収集結果と比較し、変更のないページの再抽出をスキップする
  - source_urlベースで既存スナップショットとの比較を行う
  - 既存のSnapshotStoreとの互換性を維持する
  - _Requirements: 4.5, 5.5_

- [x] 6. 四国4県のサイト定義と統合を構築する
- [x] 6.1 (P) 四国4県5サイトのYAML設定を作成する
  - 徳島県（douai-tokushima.com）のサイト定義を作成する
  - 香川県（pref.kagawa.lg.jp）の保健所サイト定義を作成する
  - 高松市（city.takamatsu.kagawa.jp）のわんにゃん高松サイト定義を作成する
  - 愛媛県（pref.ehime.jp）の動物愛護センターサイト定義を作成する
  - 松山市（city.matsuyama.ehime.jp）のはぴまるの丘サイト定義を作成する
  - 各サイトの出典（source_url）を正確に記録する設定を含める
  - _Requirements: 1.5, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

- [x] 6.2 エントリポイントの設定駆動化と既存アダプターとの共存を実装する
  - __main__.py を更新し、YAML設定からサイト一覧を読み込んで各LlmAdapterインスタンスを生成する
  - 既存の高知県アダプター（KochiAdapter）と共存し、設定で抽出方式（llm/rule-based）を切り替え可能にする
  - 全サイトのCollectorServiceによる一括処理を実装する
  - 既存のAnimalRepositoryを使ってデータベースに保存する
  - サポート対象プロバイダー指定時にプロバイダーインスタンスを生成する仕組みを実装する
  - _Requirements: 4.3, 4.4, 8.2, 8.5, 8.6_

- [x] 7. 統合テストとE2Eテストを構築する
- [x] 7.1 LlmAdapter統合テストを作成する
  - モックLlmProviderを使ったfetch_animal_list → extract_animal_details → normalizeの一連フロー確認
  - LlmAdapter + CollectorServiceの既存パイプライン統合動作テスト
  - エラーケーステスト: サイト接続失敗時の他サイト処理継続、API失敗時のリトライとスキップ
  - 1サイトのエラーが他サイトに影響しないことの確認
  - _Requirements: 4.1, 4.2, 6.2, 3.8_

- [ ]* 7.2 四国サイトのE2Eテストを作成する
  - 各サイトに対する実際のHTTP取得 + LLM抽出の動作確認テスト（CI skip、手動実行）
  - 抽出結果の品質チェック（speciesが犬/猫、shelter_dateが有効な日付）
  - robots.txtの尊重とリクエスト間隔（最低1秒）の確認
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.7_

## Requirements Coverage

| Requirement | Tasks |
|-------------|-------|
| 1 | 1.1, 1.2, 6.1 |
| 2 | 3.3, 4.1, 7.1 |
| 3 | 3.2, 3.3, 3.4, 4.2, 7.1 |
| 4 | 4.3, 5.3, 6.2, 7.1 |
| 5 | 2.1, 2.2, 3.2, 5.1, 5.3 |
| 6 | 5.1, 5.2, 7.1 |
| 7 | 6.1, 7.2 |
| 8 | 1.1, 3.1, 3.2, 6.2 |
