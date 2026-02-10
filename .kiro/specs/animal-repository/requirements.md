# Requirements Document

## Introduction

animal-repository は、正規化された保護動物データを長期的に蓄積・管理するためのデータ基盤機能です。既存の animal-api-persistence（基本的なCRUD操作）を拡張し、以下の高度な機能を提供します：

- **ステータス管理**: 動物の状態（収容中、譲渡済み、返還済み、死亡）を追跡
- **データ保持ポリシー**: 譲渡後6ヶ月間のデータ保持と自動アーカイブ
- **画像永続化**: 外部URL依存からの脱却、画像ファイルのローカル保存

既存のAnimalモデル、AnimalRepository、categoryフィールドとの完全な後方互換性を維持します。

## Requirements

### Requirement 1: ステータス管理

**Objective:** As a 運用者, I want 動物のステータス（収容中/譲渡済み/返還済み/死亡）を管理できる機能, so that 動物の状態変化を正確に追跡し、適切な情報を公開できる。

#### Acceptance Criteria
1.1 The Animal Repository shall ステータスフィールド（`status`）を動物レコードに持ち、'sheltered'（収容中）、'adopted'（譲渡済み）、'returned'（返還済み）、'deceased'（死亡）の4値を許容する。
1.2 When 新規動物データが収集された場合, the Animal Repository shall デフォルトステータス 'sheltered' を設定する。
1.3 When ステータスが変更された場合, the Animal Repository shall ステータス変更日時（`status_changed_at`）を記録する。
1.4 The Animal Repository shall ステータス変更履歴（`status_history`）を保持し、過去のステータス遷移を追跡可能にする。
1.5 When ステータスが 'adopted' または 'returned' に変更された場合, the Animal Repository shall 成果日（`outcome_date`）を記録する。
1.6 The Animal Repository shall ステータスでのフィルタリング検索をサポートする。

### Requirement 2: データ保持ポリシー

**Objective:** As a システム管理者, I want 譲渡完了後6ヶ月間データを保持し、期間経過後は自動アーカイブする機能, so that ストレージコストを最適化しながら、必要な期間はデータにアクセスできる。

#### Acceptance Criteria
2.1 The Animal Repository shall ステータスが 'adopted' または 'returned' に変更されてから6ヶ月間、動物データをアクティブテーブルに保持する。
2.2 When 保持期間（6ヶ月）が経過した場合, the Animal Repository shall 該当データをアーカイブテーブルに移動する。
2.3 The Animal Repository shall アーカイブデータへの読み取り専用アクセスを提供する。
2.4 The Animal Repository shall 保持期間をシステム設定で変更可能にする（デフォルト: 180日）。
2.5 While データがアーカイブ処理中, the Animal Repository shall 処理対象データへのアクセスをブロックせず、一貫性を保証する。
2.6 The Animal Repository shall アーカイブ処理の実行ログ（処理件数、処理時間、エラー）を記録する。
2.7 If アーカイブ処理中にエラーが発生した場合, the Animal Repository shall 処理を中断し、運用者に通知する。

### Requirement 3: 画像永続化

**Objective:** As a システム運用者, I want 外部画像URLに依存せず、画像ファイルをローカルに保存する機能, so that 外部サイトの構造変更やリンク切れによる画像消失を防止できる。

#### Acceptance Criteria
3.1 When 新規動物データが収集された場合, the Animal Repository shall 画像URLから画像ファイルをダウンロードし、ローカルストレージに保存する。
3.2 The Animal Repository shall 保存した画像に一意のファイル名（UUID + オリジナル拡張子）を付与する。
3.3 The Animal Repository shall 画像のローカルパス（`local_image_paths`）を動物レコードに記録し、元のURL（`image_urls`）も保持する。
3.4 While 画像ダウンロード中, the Animal Repository shall 元の画像URLを使用可能な状態に維持する（ダウンロード完了まで）。
3.5 If 画像ダウンロードに失敗した場合, the Animal Repository shall エラーをログに記録し、元のURLのみを保持して処理を継続する。
3.6 The Animal Repository shall 画像ファイルの重複保存を防止するため、ハッシュベースの重複検出を行う。
3.7 When 動物データがアーカイブされた場合, the Animal Repository shall 関連する画像ファイルもアーカイブストレージに移動する。
3.8 The Animal Repository shall サポートする画像形式（JPEG、PNG、GIF、WebP）を検証し、非対応形式は拒否する。

### Requirement 4: データ整合性

**Objective:** As a 開発者, I want データの整合性と一貫性を保証する機能, so that 信頼性の高いデータ基盤を維持できる。

#### Acceptance Criteria
4.1 The Animal Repository shall source_url のユニーク制約を維持し、重複データの挿入を防止する。
4.2 The Animal Repository shall ステータス遷移の妥当性を検証する（例: 'deceased' から他のステータスへの遷移は禁止）。
4.3 When 不正なステータス遷移が試行された場合, the Animal Repository shall ValidationError を発生させ、変更を拒否する。
4.4 The Animal Repository shall トランザクション内でデータ更新とステータス履歴記録を原子的に実行する。
4.5 If データベーストランザクションが失敗した場合, the Animal Repository shall 変更をロールバックし、エラーを通知する。

### Requirement 5: 後方互換性

**Objective:** As a 開発者, I want 既存のAPI・モデルとの後方互換性を維持する機能, so that 既存のシステム（public-web-portal、notification-manager）を変更せずに新機能を導入できる。

#### Acceptance Criteria
5.1 The Animal Repository shall 既存のAnimalDataモデルとの互換性を維持し、新フィールドはオプショナルとする。
5.2 The Animal Repository shall 既存のlist_animals、get_animal_by_id APIの動作を変更しない。
5.3 When ステータスフィルタが指定されない場合, the Animal Repository shall 従来通り全ステータスのデータを返却する（ただし、アーカイブ済みを除く）。
5.4 The Animal Repository shall 既存のcategoryフィールド（'adoption', 'lost'）との共存をサポートする。
5.5 The Animal Repository shall Alembicマイグレーションで既存データに影響を与えずにスキーマを拡張する。

### Requirement 6: 運用・監視

**Objective:** As a 運用者, I want システムの状態を監視し、問題を早期発見できる機能, so that 安定したサービス運用を維持できる。

#### Acceptance Criteria
6.1 The Animal Repository shall ステータス別の動物件数を集計するメトリクスを提供する。
6.2 The Animal Repository shall 画像ストレージの使用量を監視し、閾値超過時にアラートを発生させる。
6.3 The Animal Repository shall アーカイブ対象データ件数の日次レポートを生成する。
6.4 When 画像ダウンロード失敗率が閾値（10%）を超えた場合, the Animal Repository shall 運用者にアラートを送信する。
6.5 The Animal Repository shall 全ての状態変更操作を監査ログに記録する。
