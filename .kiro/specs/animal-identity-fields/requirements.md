# Requirements Document

## Project Description (Input)
個体識別情報（品種・仮名・性格/特徴・管理番号）の収集・保存・公開・検索を可能にする。

### 背景・課題
現在 oneco は保護動物の species/sex/age/color/size/location/phone しか保存しておらず、「この子が誰か」を伝える個体識別情報を捨てている。具体的には: (1) 高知アダプターは「品種=柴犬」を読むが犬猫判定にだけ使い品種名を破棄、(2) 柏アダプターは「性格・特徴」の自由文を読むが年齢抽出にだけ使い本文を破棄、(3) LLM抽出(groq_provider)はそもそも品種/性格を項目として拾っていない。根本原因は RawAnimalData / AnimalData / Animal(ORM) に受け皿フィールドが無いこと。

### 使命との関係（殺処分ゼロ）
個体識別情報の欠落が使命の律速になっている。(a)迷子の再会は品種・特徴・収容番号が同定の決め手、(b)譲渡コンバージョンは仮名と性格が最大の引き金、(c)q検索は「チワワ」「人懐っこい」で探せると謳うが保存していないので機能していない（看板倒れ）。

### スコープ（4フィールドを設計）
- **breed（品種）**: 構造化された単一値の犬種・猫種名（例: 柴犬、チワワ、雑種）。PIIリスク低。検索価値高。
- **name（仮名/愛称）**: 施設が付けた呼び名（例: ポチ）。
- **description（性格・特徴）**: 自由記述テキスト（例: 人懐っこい、シャイ）。★PII（電話番号・氏名等）が混入しうるため伏字処理が必須。
- **management_number（収容番号/管理番号）**: 個体識別番号（例: R7-249）。迷子の再会で同定の決め手。

### 影響範囲（層）
DBスキーマ（Alembic migration・本番Supabase、nullable追加で後方互換）→ ドメインモデル（RawAnimalData/AnimalData）→ ORM(Animal)→ DataNormalizer（descriptionへのPII伏字適用、各フィールドの長さ上限）→ 公開APIスキーマ（AnimalPublic）→ frontend（AnimalCard/AnimalDetailClientの表示・型）→ q検索（breed/description/nameをOR対象に追加）→ LLM抽出スキーマ（groq_providerのJSON schema拡張）→ 各rule-basedアダプターの配線（既に読んでいる箇所をフィールドに渡す。100+アダプターは段階的）。

### 制約・方針
- migration は nullable カラム追加で後方互換を保つ。既存データは次回収集で再正規化。
- description の自由文は DataNormalizer._redact_pii（既存）を必ず適用し PII を伏字化する。lost の location 粗粒度化と整合させる。
- rule-based 100% 運用方針（project_extraction_strategy）と整合。アダプター配線は「既に解析している値を渡すだけ」を優先し、新規抽出ロジック追加は最小限。
- 全4フィールドを設計するが、実装は breed → description → name/management_number のようにスライスして段階的に PR 化できる構造にする。
- 公開時の表示は欠損(None)を許容し、欠損フィールドはUIで非表示にする（充填は段階的なため）。

### 完成の定義
4フィールドが収集→正規化(PII伏字含む)→保存→公開API→frontend表示→q検索 まで一気通貫で流れ、少なくとも代表アダプター（高知・柏等の既に解析済みサイト）とLLM経路で実際に値が入ること。TDD で各層をカバー。

## Introduction
本仕様は、保護動物の「個体識別情報」4フィールド（breed=品種, name=仮名, description=性格・特徴, management_number=管理番号）を、収集パイプライン・データモデル・永続化層・公開API・フロントエンド・キーワード検索まで一気通貫で扱えるようにするための要件を定義する。

これらは「殺処分ゼロ」という使命に対し、迷子の再会（同定の決め手）と譲渡コンバージョン（情緒的訴求）、および検索の実効性を直接高める。全フィールドは任意（nullable）であり、サイトによって取得可否が異なることを前提に、欠損を許容しながら段階的に充填していく設計とする。description は自由記述のため第三者の個人情報（電話番号・氏名等）が混入しうるリスクがあり、PII 伏字を必須とする。

対象システム名:
- **データ収集システム**: rule-based アダプター群 + LLM 抽出経路 + CollectorService。
- **DataNormalizer**: 正規化ドメインサービス。
- **保護動物リポジトリ**: 永続化層（Animal ORM + AnimalRepository + Alembic）。
- **公開API**: `GET /animals` 系の REST API。
- **フロントエンド**: Next.js 公開ポータル（AnimalCard / 動物詳細）。

## Requirements

### Requirement 1: 個体識別フィールドのデータモデル拡張
**Objective:** 運営者として、4つの個体識別フィールドを保持できるデータモデルとスキーマが欲しい。そうすれば、収集した品種・仮名・性格・管理番号を捨てずに永続化できる。

#### Acceptance Criteria
1. The 保護動物リポジトリ shall Animal テーブルに `breed`, `name`, `description`, `management_number` の4カラムを nullable として持つ。
2. The データ収集システム shall RawAnimalData と AnimalData に `breed`, `name`, `description`, `management_number` の4フィールドを任意（既定 None）として持つ。
3. The 公開API shall AnimalPublic スキーマに `breed`, `name`, `description`, `management_number` を任意フィールドとして含める。
4. When 既存DBに対して当該マイグレーションを適用する, the 保護動物リポジトリ shall 既存行をエラーなく保持し、新カラムを NULL として埋める（後方互換）。
5. While いずれかのフィールドが未取得（None）である, the 保護動物リポジトリ shall その動物レコードの保存・取得を従来どおり成功させる。

### Requirement 2: 個体識別情報の正規化とPII保護
**Objective:** 運営者として、保存前に個体識別情報を安全な形に正規化したい。そうすれば、自由記述に混入する第三者の個人情報を公開せず、DB制約も超えない。

#### Acceptance Criteria
1. When DataNormalizer が description を正規化する, the DataNormalizer shall 既存の PII 伏字処理（電話番号・メールアドレスを伏字化）を description に適用する。
2. If 正規化後のフィールド値が DB の長さ上限を超える, then the DataNormalizer shall 上限内に丸めて保存可能な形にする。
3. If 入力フィールドが空文字または空白のみである, then the DataNormalizer shall そのフィールドを None として扱う。
4. The DataNormalizer shall breed / name / management_number を表示用に過不足なくトリム（前後空白除去）した値で返す。
5. The DataNormalizer shall description 内の電話番号・メールアドレスを伏字化する。ただし第三者の氏名（人名）は伏字対象外とする（形態素解析を要するため本仕様の非対象。高リスクの電話/メールはカバーする）。
6. The DataNormalizer shall management_number に PII 伏字を適用しない（番号の誤伏字を避けるため）。

### Requirement 3: 収集経路での個体識別情報の取得
**Objective:** 里親希望者・迷子の飼い主として、サイトに載っている品種や性格が oneco にも反映されてほしい。そうすれば、探している子をより正確に見つけられる。

#### Acceptance Criteria
1. Where rule-based アダプターが既に品種・性格・仮名・管理番号を解析している, the データ収集システム shall その解析済みの値を対応フィールドへ渡して保存する（新規抽出ロジック追加を最小限にする）。
2. When LLM 抽出経路が動物詳細ページを構造化抽出する, the データ収集システム shall breed / name / description / management_number を抽出スキーマの任意項目として取得する。
3. If あるサイトに当該情報が存在しない, then the データ収集システム shall 当該フィールドを None のままにして収集を継続する（欠損を許容）。
4. When 代表アダプター（高知・柏等の既に解析済みサイト）で収集を実行する, the データ収集システム shall 少なくとも1つ以上の個体識別フィールドに実際の値を保存する。
5. The データ収集システム shall 既存フィールド（species/sex/age/color/size/location/phone）の収集結果を本変更によって悪化させない。

### Requirement 4: 公開APIでの提供と検索
**Objective:** 里親希望者として、品種のキーワードで動物を横断検索したい。そうすれば、「チワワ」「柴犬」のような条件で目的の子に辿り着ける。name/description は表示で確認する。

#### Acceptance Criteria
1. When 公開API が動物データを返す, the 公開API shall 値が存在する場合に breed / name / description / management_number を応答に含める。
2. When `GET /animals?q=<キーワード>` が呼ばれる, the 公開API shall breed を既存の検索対象（species/color/size/location/prefecture）に加えた OR 部分一致で検索する。name / description / management_number は検索対象に含めない（表示のみ）。
3. When breed をキーワード検索する, the 公開API shall カタカナとひらがなの差異を無視して照合する（保存値と検索語を片方の仮名に正規化して比較。例: 「チワワ」と「ちわわ」が相互にヒット）。漢字の読み変換（例: 「柴犬」と「しばいぬ」）は本仕様の非対象とする。
4. While あるフィールドが None である, the 公開API shall そのフィールドを応答から省略するか null として返し、検索のヒット判定では無視する。
5. The 公開API shall 検索キーワードについて、既存の LIKE エスケープと最大長の方針を踏襲する。
6. If description が公開対象として保存されている, then the 公開API shall PII 伏字済みの値のみを返す（伏字前の原文を返さない）。

### Requirement 5: フロントエンドでの表示
**Objective:** 里親希望者・迷子の飼い主として、一覧と詳細で品種・仮名・性格・管理番号を見たい。そうすれば、この子の魅力や同定の手掛かりが分かる。

#### Acceptance Criteria
1. Where 動物に仮名（name）または品種（breed）が存在する, the フロントエンド shall 一覧カードの見出し付近にそれらを表示する。
2. Where 動物に性格・特徴（description）が存在する, the フロントエンド shall 動物詳細ページにそれを表示する。
3. Where 動物に管理番号（management_number）が存在する, the フロントエンド shall 同定に役立つ位置（詳細ページ）に表示する。
4. If いずれかの個体識別フィールドが None である, then the フロントエンド shall その項目を描画せず、レイアウトを崩さない。
5. The フロントエンド shall 個体識別フィールドの型定義（AnimalPublic 相当）を任意フィールドとして追加し、型エラーなくビルドできる。

### Requirement 6: 後方互換と段階的ロールアウト
**Objective:** 運営者として、本機能を一度に全アダプターへ展開せず、安全に段階導入したい。そうすれば、本番DBや既存収集を壊さずに価値を順次提供できる。

#### Acceptance Criteria
1. The 保護動物リポジトリ shall 4フィールドすべてを nullable とし、未充填のサイト・既存行が存在しても整合性を保つ。
2. When breed のみを先行実装した状態で収集・公開を行う, the データ収集システム shall 他の3フィールドが未配線でもエラーなく動作する（スライス可能性）。
3. While 個体識別フィールドが部分的にしか充填されていない, the フロントエンド shall 充填済みフィールドのみを表示して破綻しない。
4. The データ収集システム shall 本変更のために既存データの破壊的移行（バックフィル必須化）を要求しない（既存行は次回収集で自然に充填される）。
5. The データ収集システム / DataNormalizer / 公開API / フロントエンド shall 各層の変更に対して TDD（Red→Green）でテストを追加し、リグレッションが無いことを既存テストスイートで確認できる。
