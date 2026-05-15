# Requirements Document

## Project Description (Input)
data-collector-rule-based-migration: 既存データコレクター(209サイト分のYAML設定)を、現状のLLM抽出（Anthropic/Groq）から完全rule-based抽出へ移行する。事前解析で209サイトは92ユニークテンプレートに集約済み(scripts/template_analysis_2026-05-15.md)。既存KochiAdapter(798行)を参考に共通基底クラス(WordPressListAdapter/SinglePageTableAdapter/PlaywrightAdapter/PdfTableAdapter等)を整備し、各テンプレートを実装する。LLMプロバイダのコードは削除せず、収益化後に default_provider を anthropic に戻すだけで復帰可能な状態を維持。rule失敗時のLLMフォールバックも残す。リリース基準は92テンプレート全てのrule-based実装完了。種別内訳: standard(list+detail) 44サイト / single_page 129 / requires_js 25 / pdf 11。

## Introduction

本仕様は、oneco データコレクターの抽出方式を **LLM ベース** から **完全 rule-based** へ移行する基盤と運用ルールを定義する。

事前解析（`scripts/template_analysis_2026-05-15.md`）により、209サイトは **92 ユニークテンプレート** に集約可能であることが判明した。各テンプレートに対応する rule-based アダプターを実装することで、(1) 月次 LLM API コストを $0 に抑制し、(2) 抽出精度の決定論性を高め、(3) 個人開発者が燃え尽きることなく長期運用できる体制を構築する。

LLM プロバイダのコード（`anthropic_provider.py` / `groq_provider.py` / `fallback_provider.py`）は削除せず、(a) 収益化達成時に `default_provider` 設定を切替えるだけで完全 LLM 抽出に復帰可能な状態、(b) rule 抽出が破損したサイトに対する救済策、として温存する。

リリース基準は **92 テンプレート全てのrule-based実装完了** とする。

## Requirements

### Requirement 1: アダプター基盤（共通基底クラス）

**Objective:** 開発者として、サイト別アダプター実装時に重複コードを書きたくない。共通パターンを基底クラスとして提供することで、新規アダプターを最小コードで追加できるようにするため。

#### Acceptance Criteria
1. The Rule-Based Extraction Engine shall 4種類の基底アダプタークラス（`WordPressListAdapter`、`SinglePageTableAdapter`、`PlaywrightAdapter`、`PdfTableAdapter`）を提供する
2. The Rule-Based Extraction Engine shall 既存の `MunicipalityAdapter` インターフェース（`fetch_animal_list`、`extract_animal_details`、`normalize`）を全ての基底クラスで実装する
3. The Rule-Based Extraction Engine shall 共通処理（HTTP リクエスト、HTML パース、URL正規化、エラー処理）を基底クラスに集約する
4. When 派生クラスが基底クラスを継承する場合, the Rule-Based Extraction Engine shall サイト固有の CSS セレクタ・テキストパターン定義のみで動作可能にする
5. The Rule-Based Extraction Engine shall 既存の `KochiAdapter`（798行、`adapters/kochi_adapter.py`）を参照実装として維持し、新基底クラスと共存させる

### Requirement 2: 92テンプレートに対応する具体アダプター実装

**Objective:** プロダクトオーナーとして、209 全サイトのデータを LLM に依存せず取得したい。テンプレート集約解析で特定された 92 ユニーク構造を全てカバーするため。

#### Acceptance Criteria
1. The Rule-Based Extraction Engine shall 92 ユニークテンプレート全てに対応する rule-based アダプターを実装する
2. The Rule-Based Extraction Engine shall 同一テンプレートを共有する複数サイトを 1 つのアダプターでカバーする
3. While 同一ドメインで複数サイトが存在する場合, the Rule-Based Extraction Engine shall サイト別パラメータ（カテゴリ、URL クエリ、フィルタ等）のみを設定で切替可能にする
4. The Rule-Based Extraction Engine shall 種別ごとの実装数を以下に揃える: standard(list+detail) 44 サイト / single_page 129 サイト / requires_js 25 サイト / pdf 11 サイト
5. When 新規サイトが既存テンプレートと一致する場合, the Rule-Based Extraction Engine shall sites.yaml への 1 エントリ追加のみで対応可能にする

### Requirement 3: 抽出方式切替の透過性

**Objective:** システム運用者として、LLM 抽出から rule-based 抽出への切替を段階的かつ無停止で行いたい。既存のフロントエンド・DB・API・通知系に影響を与えないため。

#### Acceptance Criteria
1. The Rule-Based Extraction Engine shall サイト別に `extraction: "rule-based" | "llm"` を `sites.yaml` で指定可能にする
2. The Rule-Based Extraction Engine shall rule-based 抽出結果を既存の `RawAnimalData` モデルとして出力する
3. The Rule-Based Extraction Engine shall 抽出後の処理（`DataNormalizer` → `AnimalData` → `AnimalRepository` → 通知）を一切変更せず再利用する
4. When `default_provider` 設定が `rule-based` の場合, the Rule-Based Extraction Engine shall 全サイトをデフォルトで rule-based 抽出する
5. When 個別サイトに `extraction: "llm"` が明示指定されている場合, the Rule-Based Extraction Engine shall 当該サイトのみ LLM 抽出を継続する
6. The Rule-Based Extraction Engine shall 既存スナップショット保存・差分検知ロジックと完全互換にする

### Requirement 4: LLM プロバイダの温存とフォールバック

**Objective:** プロダクトオーナーとして、収益化達成時に容易に LLM 抽出へ復帰したい。また、rule 破損時にも完全停止を避けるため。

#### Acceptance Criteria
1. The Rule-Based Extraction Engine shall 既存の LLM プロバイダ実装（`anthropic_provider.py` / `groq_provider.py` / `fallback_provider.py`）を削除しない
2. The Rule-Based Extraction Engine shall `__main__.py` の `PROVIDER_REGISTRY` に LLM プロバイダエントリを保持する
3. When `sites.yaml` の `default_provider` が `anthropic` 等の LLM プロバイダ名に変更された場合, the Rule-Based Extraction Engine shall 全サイトを LLM 抽出に復帰させる
4. Where rule-based 抽出がエラー終了したサイトに `fallback_to_llm: true` 設定がある場合, the Rule-Based Extraction Engine shall 当該サイトを LLM 抽出で再試行する
5. The Rule-Based Extraction Engine shall LLM 抽出に必要な API キー設定手順をドキュメント化し、再有効化を 1 PR で完結可能にする

### Requirement 5: TDD によるアダプター品質保証

**Objective:** 開発者として、各アダプターが期待通りに動作することを継続的に検証したい。本番稼働中のサイトHTML変更による静かな破損を防ぐため。

#### Acceptance Criteria
1. The Rule-Based Extraction Engine shall 各アダプターに対して固定 HTML スナップショットを使ったユニットテストを提供する
2. The Rule-Based Extraction Engine shall 期待される `RawAnimalData` フィールド（species, sex, age, color, size, shelter_date, location, phone, image_urls）を全テストで検証する
3. While 新規アダプターを追加する場合, the Rule-Based Extraction Engine shall 最低 1 件の HTML スナップショット + 期待出力 fixture を必須とする
4. The Rule-Based Extraction Engine shall pytest で全アダプターのテストが PASS することを CI で検証する
5. When アダプター実装が `RawAnimalData` バリデーションを満たせない場合, the Rule-Based Extraction Engine shall ユニットテストを失敗させる

### Requirement 6: 抽出失敗の検知と運用通知

**Objective:** 運営者として、サイト HTML 変更や DOM 構造変化による rule 破損を早期に検知したい。リリース後の保守工数を予見可能にするため。

#### Acceptance Criteria
1. When rule-based 抽出が必須フィールドの取得に失敗した場合, the Rule-Based Extraction Engine shall エラーログにサイト名・該当 selector・取得失敗フィールドを記録する
2. When 1 サイトの抽出件数が前回スナップショットの 50% 未満になった場合, the Rule-Based Extraction Engine shall 既存の Slack 通知（per-site Warning/Critical）を発火する
3. The Rule-Based Extraction Engine shall 部分失敗（一部サイト失敗、他サイト成功）でも CI ジョブ全体を成功扱いとする（既存仕様継承）
4. When サイトが連続 3 回エラーを返した場合, the Rule-Based Extraction Engine shall 当該サイトを「要修正」リストに記録する
5. The Rule-Based Extraction Engine shall 抽出結果サマリ（成功サイト数、失敗サイト数、抽出動物総数）を実行ごとに出力する

### Requirement 7: 段階的マイグレーション戦略

**Objective:** プロダクトオーナーとして、92 テンプレート全実装完了までの間も既存運用を継続したい。実装途上で動物データの公開が止まらないため。

#### Acceptance Criteria
1. The Rule-Based Extraction Engine shall 実装済みアダプターと未実装サイトを混在運用可能にする
2. While あるサイトのアダプターが未実装の場合, the Rule-Based Extraction Engine shall 当該サイトを既存 LLM 抽出で稼働させる
3. The Rule-Based Extraction Engine shall アダプター実装の進捗を追跡可能にする（実装済みテンプレ数 / 92）
4. When アダプター実装が完了したテンプレートが存在する場合, the Rule-Based Extraction Engine shall 該当サイトの `extraction` を `rule-based` に切替する PR で段階的にロールアウト可能にする
5. The Rule-Based Extraction Engine shall リリース基準（92 テンプレート全実装完了）達成後、`default_provider` を `rule-based` に切替える最終 PR を発行可能な状態にする

### Requirement 8: 性能とリソース効率

**Objective:** システム運用者として、rule-based 化により CI 実行時間を短縮し、リソース使用量を削減したい。GitHub Actions の 6 時間ジョブ上限内に余裕を持たせるため。

#### Acceptance Criteria
1. The Rule-Based Extraction Engine shall rule-based 抽出を LLM 抽出より高速に実行する（ネットワーク I/O 除く処理時間）
2. The Rule-Based Extraction Engine shall 1 サイトあたりの抽出時間を 60 秒以内（standard・single_page）、180 秒以内（requires_js）に収める
3. The Rule-Based Extraction Engine shall 既存の `SITE_TIMEOUT_SEC` / `SITE_TIMEOUT_JS_SEC` 仕様を継承する
4. The Rule-Based Extraction Engine shall 209 サイト全件抽出を GitHub Actions の 6 時間以内に完了させる
5. The Rule-Based Extraction Engine shall LLM API 呼び出しを 0 回にする（`fallback_to_llm` 発動時を除く）

### Requirement 9: ドキュメント整備

**Objective:** 将来の開発者（自分自身を含む）として、新規サイト追加・既存アダプター修正の手順を理解したい。コード読解だけに頼らず効率的に保守作業を行うため。

#### Acceptance Criteria
1. The Rule-Based Extraction Engine shall 基底クラス使用方法のドキュメントを `docs/` または該当モジュールの docstring に整備する
2. The Rule-Based Extraction Engine shall 「新規サイト追加手順」「既存アダプター修正手順」を README.md またはガイドドキュメントに記載する
3. The Rule-Based Extraction Engine shall LLM プロバイダ復帰手順（`default_provider` 切替、API キー設定）をドキュメント化する
4. Where テンプレート集約解析が更新される場合, the Rule-Based Extraction Engine shall `scripts/template_analysis_*.md` を最新版に維持する
5. The Rule-Based Extraction Engine shall 各アダプターのソースコードに対象サイト名・テンプレート種別をコメントで明記する
