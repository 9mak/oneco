# Requirements Document

## Project Description (Input)
category フィールド追加 - 譲渡対象/迷子の区別

## Introduction

本機能は、保護動物データに `category`（カテゴリ）フィールドを追加し、「譲渡対象」と「迷子」を区別できるようにするものです。

### 背景

現在のシステムでは、高知県アダプターが以下の2つのページから動物情報を収集しています：
- **譲渡情報（/jouto/）**: 新しい飼い主を探している動物
- **迷子情報（/maigo/）**: 飼い主の迎えを待つ動物

しかし、現在のデータモデル（`AnimalData`、`Animal` テーブル、`AnimalPublic` スキーマ）にはカテゴリを示すフィールドがなく、収集後にどのページから取得したデータかを区別できません。

### 影響範囲

以下のコンポーネントを拡張する必要があります：
1. **data-collector**: `RawAnimalData`、`AnimalData` モデル
2. **animal-api-persistence**: `Animal` テーブル、`AnimalPublic` スキーマ、API フィルタ
3. **KochiAdapter**: カテゴリ判定ロジック（収集元URLから判定）

### カテゴリ値

| カテゴリ | 値 | 説明 |
|---------|-----|------|
| 譲渡対象 | `adoption` | 新しい飼い主を探している動物 |
| 迷子 | `lost` | 飼い主の迎えを待つ動物 |

## Requirements

### Requirement 1: ドメインモデルへのカテゴリフィールド追加

**Objective:** As a システム開発者, I want 動物データにカテゴリ情報を含めたい, so that 譲渡対象と迷子を区別してデータ処理できる

#### Acceptance Criteria

1. The RawAnimalData shall `category` フィールド（文字列型）を持つ
2. The AnimalData shall `category` フィールド（'adoption' または 'lost'）を持つ
3. The AnimalData shall `category` フィールドに対して2値制約バリデーション（'adoption', 'lost'）を適用する
4. If 無効なカテゴリ値が渡された, then the AnimalData shall バリデーションエラーを発生させる
5. The AnimalData shall `category` フィールドを必須フィールドとする

### Requirement 2: データベーススキーマへのカテゴリカラム追加

**Objective:** As a システム管理者, I want カテゴリ情報をデータベースに永続化したい, so that 過去のデータも含めてカテゴリで検索できる

#### Acceptance Criteria

1. The Animal テーブル shall `category` カラム（VARCHAR(20)、NOT NULL）を持つ
2. The Animal テーブル shall `category` カラムにインデックスを作成する
3. The システム shall Alembic マイグレーションで `category` カラムを追加する
4. When 既存データにマイグレーションを適用する, the システム shall デフォルト値 'adoption' を設定する
5. The Animal テーブル shall 複合検索インデックスに `category` を含める

### Requirement 3: APIスキーマへのカテゴリフィールド追加

**Objective:** As a 外部システム開発者, I want APIレスポンスにカテゴリ情報を含めたい, so that クライアント側でカテゴリ別の表示ができる

#### Acceptance Criteria

1. The AnimalPublic スキーマ shall `category` フィールド（文字列型）を持つ
2. The GET /animals エンドポイント shall `category` クエリパラメータを受け取る
3. When GET /animals?category=adoption リクエストが送信された, the API shall 譲渡対象の動物のみを返却する
4. When GET /animals?category=lost リクエストが送信された, the API shall 迷子の動物のみを返却する
5. When category パラメータが省略された, the API shall 全カテゴリの動物を返却する
6. If 無効なカテゴリ値がクエリパラメータに指定された, then the API shall HTTP 400 エラーを返却する

### Requirement 4: アダプターでのカテゴリ判定

**Objective:** As a データ収集システム, I want 収集元URLからカテゴリを自動判定したい, so that 手動でカテゴリを設定する必要がない

#### Acceptance Criteria

1. When KochiAdapter が /jouto/ ページから動物情報を収集した, the KochiAdapter shall category を 'adoption' に設定する
2. When KochiAdapter が /maigo/ ページから動物情報を収集した, the KochiAdapter shall category を 'lost' に設定する
3. The MunicipalityAdapter インターフェース shall カテゴリ情報を返却するメソッドをサポートする
4. Where 新しい自治体アダプターを追加する場合, the アダプター shall 同様のカテゴリ判定ロジックを実装する
5. If カテゴリが判定できない場合, then the アダプター shall デフォルト値 'adoption' を設定しログに警告を出力する

### Requirement 5: 既存データとの後方互換性

**Objective:** As a システム管理者, I want 既存データに影響を与えずにカテゴリを追加したい, so that 本番環境への移行がスムーズに行える

#### Acceptance Criteria

1. The マイグレーション shall 既存の全レコードに対してデフォルトカテゴリ 'adoption' を設定する
2. The API shall category フィールドを含まないリクエストを引き続き受け付ける
3. The システム shall マイグレーション後も既存のAPIクライアントが動作し続けることを保証する
4. When マイグレーションを実行した, the システム shall ロールバック可能なマイグレーションスクリプトを提供する
5. The システム shall カテゴリ追加前後でsource_urlの一意性制約を維持する

---

## 技術的補足

### カテゴリ値の選定理由

日本語の「譲渡対象」「迷子」ではなく英語の `adoption` / `lost` を使用する理由：
- APIパラメータとしての一貫性（他のフィールドも英語）
- URLエンコーディングの回避
- 国際化対応の容易さ

### 影響を受けるファイル

| レイヤー | ファイル | 変更内容 |
|---------|---------|---------|
| Domain | `src/data_collector/domain/models.py` | RawAnimalData, AnimalData に category 追加 |
| Infrastructure/DB | `src/data_collector/infrastructure/database/models.py` | Animal に category カラム追加 |
| Infrastructure/API | `src/data_collector/infrastructure/api/schemas.py` | AnimalPublic に category 追加 |
| Infrastructure/API | `src/data_collector/infrastructure/api/routes.py` | category フィルタ追加 |
| Infrastructure/DB | `src/data_collector/infrastructure/database/repository.py` | category フィルタ対応 |
| Adapter | `src/data_collector/adapters/kochi_adapter.py` | カテゴリ判定ロジック追加 |
| Migration | `alembic/versions/` | category カラム追加マイグレーション |

